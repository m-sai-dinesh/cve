"""Config and build-file parsing (PRD §8.1 steps 3c/3d).

Config: DB URLs, file paths, hard-coded hosts, ports, secret patterns. Secret
*values are masked at parse time* - the raw value never reaches storage, logs or
an LLM (PRD §15 data minimisation).

Build: third-party libraries + versions, with an end-of-life check.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from ....core.llm import looks_secret, mask_secret

JDBC_RE = re.compile(r"(?i)\b(jdbc:[a-z0-9]+:[^\s\"'<>;,]+)")
URL_RE = re.compile(r"(?i)\b((?:https?|ftp|ldap|amqp|mongodb|redis)://[^\s\"'<>;,]+)")
IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
WIN_PATH_RE = re.compile(r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|\\\\\\\\)[^\s\"'<>;,|*?]+")
UNC_RE = re.compile(r"\\\\\\\\[A-Za-z0-9_.$-]+\\\\[^\s\"'<>;,]+")
UNIX_PATH_RE = re.compile(r"(?<![\w:/])/(?:opt|var|mnt|srv|home|usr|tmp|data)/[^\s\"'<>;,:]+")
PORT_RE = re.compile(r"(?i)\b(?:port|\.port)\s*[:=]\s*(\d{2,5})\b")

LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@dataclass
class ConfigItem:
    key: str
    value_masked: str
    kind: str                      # host | path | secret | port | url | jdbc | setting
    file: str = ""
    line: int = 0
    is_secret: bool = False
    note: str = ""


@dataclass
class ConfigFile:
    path: str
    format: str
    items: list[ConfigItem] = field(default_factory=list)
    raw_keys: dict[str, str] = field(default_factory=dict)


def _classify(key: str, value: str) -> tuple[str, str]:
    """Return (kind, note) for a key/value pair."""
    v = (value or "").strip()
    if looks_secret(key, "") and v:
        return "secret", "credential present in a configuration file"
    if JDBC_RE.search(v):
        return "jdbc", "database connection string pinned in configuration"
    if URL_RE.search(v):
        host = URL_RE.search(v).group(1)
        if any(h in host for h in LOCALHOST_HOSTS):
            return "host", "endpoint hard-coded to localhost"
        return "url", "external endpoint hard-coded"
    if IPV4_RE.search(v):
        return "host", "literal IP address instead of a service name"
    if WIN_PATH_RE.search(v) or UNC_RE.search(v) or UNIX_PATH_RE.search(v):
        return "path", "absolute host filesystem path - breaks on a container"
    if re.fullmatch(r"\d{2,5}", v) and ("port" in key.lower()):
        return "port", "fixed port"
    kind, note = _risky_setting(key, v)
    if kind:
        return kind, note
    return "setting", ""


# Settings that are findings by their value alone. These become graph nodes so
# the compliance checks and the readiness scorer can cite them; an ordinary
# setting does not, or the graph would fill with noise.
RISKY_SETTINGS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(?i)(h2|sql|db)\.?console\.?enabled|console\.enabled"), "exposure",
     "web database console enabled - permits direct, unaudited changes to GxP data"),
    (re.compile(r"(?i)ddl-auto|hbm2ddl"), "exposure",
     "schema is altered automatically at startup - uncontrolled change to a validated structure"),
    (re.compile(r"(?i)csrf.*(disable|enabled)"), "exposure", "CSRF protection toggled off"),
    (re.compile(r"(?i)ssl\.?(enabled|verify)|verify.?ssl|tls\.?verify"), "exposure",
     "transport security disabled"),
    (re.compile(r"(?i)show.?sql|debug|trace.?enabled"), "exposure",
     "verbose diagnostics enabled - may log GxP data"),
    (re.compile(r"(?i)session\.(timeout|persistent)"), "session",
     "server-side session state - a horizontal-scaling blocker"),
    (re.compile(r"(?i)bypass|skip.?(validation|auth|esig)"), "exposure",
     "a control can be bypassed by configuration"),
]

TRUTHY = {"true", "yes", "on", "1", "enabled", "always", "update", "create", "create-drop"}


def _risky_setting(key: str, value: str) -> tuple[str, str]:
    v = (value or "").strip().strip("'\"").lower()
    for rx, kind, note in RISKY_SETTINGS:
        if not rx.search(key):
            continue
        if kind == "session":
            return kind, note
        if v in TRUTHY:
            return kind, note
        # "ssl.enabled=false" is the dangerous direction for a verify flag.
        if "verify" in key.lower() or "ssl" in key.lower():
            if v in {"false", "no", "off", "0", "disabled"}:
                return kind, note
    return "", ""


def _add(items: list[ConfigItem], key: str, value: str, path: str, line: int) -> None:
    kind, note = _classify(key, value)
    secret = kind == "secret"
    items.append(ConfigItem(
        key=key, value_masked=mask_secret(value) if secret else (value or "")[:200],
        kind=kind, file=path, line=line, is_secret=secret, note=note,
    ))


def parse_properties(text: str, path: str = "") -> ConfigFile:
    out = ConfigFile(path=path, format="properties")
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith(("#", "!")):
            continue
        m = re.match(r"([^=:]+)[=:](.*)$", s)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        out.raw_keys[key] = value
        _add(out.items, key, value, path, i)
    return out


def parse_yaml_like(text: str, path: str = "") -> ConfigFile:
    """Flatten a YAML config into dotted keys without needing valid YAML."""
    out = ConfigFile(path=path, format="yaml")
    stack: list[tuple[int, str]] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        m = re.match(r"\s*([\w.$-]+)\s*:\s*(.*)$", raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip().strip("'\"")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        dotted = ".".join([k for _, k in stack] + [key])
        if value:
            out.raw_keys[dotted] = value
            _add(out.items, dotted, value, path, i)
        else:
            stack.append((indent, key))
    return out


def parse_xml_config(text: str, path: str = "") -> ConfigFile:
    """web.xml / app.config style: <param-name>/<param-value>, <add key= value=>."""
    out = ConfigFile(path=path, format="xml")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return _scan_free_text(text, path, "xml")

    def walk(el: ET.Element) -> None:
        key = el.attrib.get("key") or el.attrib.get("name") or ""
        val = el.attrib.get("value") or ""
        if key and val:
            out.raw_keys[key] = val
            _add(out.items, key, val, path, 0)
        names = el.findall("param-name")
        values = el.findall("param-value")
        for n, v in zip(names, values):
            if n.text and v.text:
                out.raw_keys[n.text.strip()] = v.text.strip()
                _add(out.items, n.text.strip(), v.text.strip(), path, 0)
        if el.text and el.text.strip() and len(el) == 0:
            tag = el.tag.split("}")[-1]
            val = el.text.strip()
            kind, _ = _classify(tag, val)
            if kind != "setting":
                out.raw_keys[tag] = val
                _add(out.items, tag, val, path, 0)
        for child in el:
            walk(child)

    walk(root)
    return out


def _scan_free_text(text: str, path: str, fmt: str) -> ConfigFile:
    """Last resort: pull hosts/paths/URLs straight out of the text."""
    out = ConfigFile(path=path, format=fmt)
    for i, line in enumerate(text.splitlines(), start=1):
        for rx, key in ((JDBC_RE, "jdbc.url"), (URL_RE, "endpoint"), (UNC_RE, "network.share")):
            m = rx.search(line)
            if m:
                _add(out.items, key, m.group(1), path, i)
    return out


def parse_config(text: str, path: str) -> ConfigFile:
    low = path.lower()
    if low.endswith((".properties", ".env")) or low.endswith("env"):
        return parse_properties(text, path)
    if low.endswith((".yml", ".yaml")):
        return parse_yaml_like(text, path)
    if low.endswith((".xml", ".config")):
        return parse_xml_config(text, path)
    if low.endswith(".json"):
        return _scan_free_text(text, path, "json")
    return _scan_free_text(text, path, "text")


# =============================================================================
# Build files → library inventory with EOL flags
# =============================================================================

@dataclass
class Library:
    name: str
    version: str = ""
    group: str = ""
    scope: str = ""
    eol: bool = False
    eol_reason: str = ""


# Curated EOL knowledge. Each rule: (matcher, version predicate, reason).
# Dates reflect vendor end-of-support announcements for the stacks the demo and
# benchmark apps actually use; unknown libraries are never guessed as EOL.
EOL_RULES: list[tuple[str, re.Pattern[str] | None, str]] = [
    ("spring-boot", re.compile(r"^[01]\."), "Spring Boot 1.x/2.x - OSS support ended Nov 2023"),
    ("spring-boot", re.compile(r"^2\."), "Spring Boot 2.x - OSS support ended Nov 2023"),
    ("spring-core", re.compile(r"^[45]\."), "Spring Framework 4/5 - OSS support ended"),
    ("spring-framework", re.compile(r"^[45]\."), "Spring Framework 4/5 - OSS support ended"),
    ("log4j", re.compile(r"^1\."), "Log4j 1.x - end of life Aug 2015, unpatched CVEs"),
    ("log4j-core", re.compile(r"^2\.(?:[0-9]|1[0-6])\b"), "Log4j 2.x < 2.17 - Log4Shell (CVE-2021-44228) family"),
    ("junit", re.compile(r"^4\."), "JUnit 4 - superseded by JUnit 5 (Jupiter)"),
    ("hibernate-core", re.compile(r"^[45]\."), "Hibernate 4/5 - maintenance ended"),
    ("struts", None, "Apache Struts - repeated critical RCEs, migrate off"),
    ("commons-collections", re.compile(r"^3\."), "commons-collections 3.x - deserialisation RCE"),
    ("jackson-databind", re.compile(r"^2\.(?:[0-9])\b"), "jackson-databind < 2.10 - many deserialisation CVEs"),
    ("mysql-connector-java", re.compile(r"^[58]\.0\.(?:[0-9]|1[0-9])$"), "Old MySQL connector with known CVEs"),
    ("h2", re.compile(r"^1\."), "H2 1.x - console RCE (CVE-2021-42392); not a production DB"),
    ("thymeleaf", re.compile(r"^[23]\."), "Thymeleaf 2.x/3.0 - superseded"),
    ("javax.servlet-api", None, "javax.* namespace - Jakarta EE 9+ moved to jakarta.*"),
    ("quartz", re.compile(r"^1\."), "Quartz 1.x - end of life"),
    ("ojdbc", None, "Oracle JDBC - proprietary licence, a cloud migration blocker"),
]

JAVA_EOL_VERSIONS = {"1.5", "1.6", "1.7", "1.8", "5", "6", "7", "8", "9", "10", "11"}


def check_eol(name: str, version: str) -> tuple[bool, str]:
    low = name.lower()
    for key, vrx, reason in EOL_RULES:
        if key in low:
            if vrx is None or (version and vrx.match(version.lstrip("vV"))):
                return True, reason
    return False, ""


def parse_pom(text: str, path: str = "") -> tuple[list[Library], dict[str, str]]:
    """Maven pom.xml → dependencies + the properties block (for java.version)."""
    libs: list[Library] = []
    props: dict[str, str] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return libs, props
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    def t(el: ET.Element, tag: str) -> str:
        node = el.find(f"{ns}{tag}")
        return (node.text or "").strip() if node is not None and node.text else ""

    for pblock in root.findall(f"{ns}properties"):
        for child in pblock:
            props[child.tag.replace(ns, "")] = (child.text or "").strip()

    parent = root.find(f"{ns}parent")
    if parent is not None:
        a, v = t(parent, "artifactId"), t(parent, "version")
        if a:
            eol, reason = check_eol(a, v)
            libs.append(Library(name=a, version=v, group=t(parent, "groupId"),
                                scope="parent", eol=eol, eol_reason=reason))

    for dep in root.iter(f"{ns}dependency"):
        a = t(dep, "artifactId")
        if not a:
            continue
        v = t(dep, "version")
        if v.startswith("${") and v.endswith("}"):
            v = props.get(v[2:-1], v)
        eol, reason = check_eol(a, v)
        libs.append(Library(name=a, version=v, group=t(dep, "groupId"),
                            scope=t(dep, "scope") or "compile", eol=eol, eol_reason=reason))

    for jk in ("java.version", "maven.compiler.source", "maven.compiler.target"):
        jv = props.get(jk, "")
        if jv:
            eol = jv.strip() in JAVA_EOL_VERSIONS
            libs.append(Library(
                name="jdk", version=jv, group="runtime", scope="runtime", eol=eol,
                eol_reason=f"Java {jv} is past its free public-update window" if eol else "",
            ))
            break
    return libs, props


def parse_requirements(text: str, path: str = "") -> list[Library]:
    libs = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        m = re.match(r"([A-Za-z0-9_.\[\]-]+)\s*(?:[=<>!~]=?\s*([\w.*+-]+))?", s)
        if m:
            name, ver = m.group(1), m.group(2) or ""
            eol, reason = check_eol(name, ver)
            libs.append(Library(name=name, version=ver, group="pypi", eol=eol, eol_reason=reason))
    return libs


def parse_csproj(text: str, path: str = "") -> list[Library]:
    libs: list[Library] = []
    for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]*)")?', text):
        name, ver = m.group(1), m.group(2) or ""
        eol, reason = check_eol(name, ver)
        libs.append(Library(name=name, version=ver, group="nuget", eol=eol, eol_reason=reason))
    for m in re.finditer(r"<TargetFramework(?:Version)?>([^<]+)<", text):
        fw = m.group(1).strip()
        is_old = fw.lower().startswith("v") or "netframework" in fw.lower()
        libs.append(Library(
            name="target-framework", version=fw, group="runtime", eol=is_old,
            eol_reason=".NET Framework is Windows-only and closed to new features" if is_old else "",
        ))
    return libs


def parse_package_json(text: str, path: str = "") -> list[Library]:
    import json

    libs: list[Library] = []
    try:
        data = json.loads(text)
    except Exception:
        return libs
    for section in ("dependencies", "devDependencies"):
        for name, ver in (data.get(section) or {}).items():
            eol, reason = check_eol(name, str(ver).lstrip("^~"))
            libs.append(Library(name=name, version=str(ver), group="npm",
                                scope=section, eol=eol, eol_reason=reason))
    return libs


def parse_build_file(text: str, path: str) -> list[Library]:
    low = path.lower().replace("\\", "/")
    if low.endswith("pom.xml"):
        return parse_pom(text, path)[0]
    if low.endswith(".csproj") or low.endswith(".vbproj"):
        return parse_csproj(text, path)
    if low.endswith("requirements.txt"):
        return parse_requirements(text, path)
    if low.endswith("package.json"):
        return parse_package_json(text, path)
    return []
