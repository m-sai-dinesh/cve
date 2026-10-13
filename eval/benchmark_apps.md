# Benchmark Applications (PRD §19, §23)

To validate the generalizability and robustness of the ModernRx modernization pipeline beyond synthetic targets, the following benchmark applications are analyzed alongside **AcmeLIMS**:

---

## 1. AcmeLIMS (Primary Benchmark)
- **Domain:** Laboratory Information Management System (LIMS)
- **Stack:** Java 17, Spring Boot 2.7, Spring Data JPA, H2 file database
- **LOC:** ~6,200 lines across 10 functional modules
- **Planted Compliance Gaps & Architectural Smells:**
  1. `AuditTrailService`: Missing audit `reason` column on `AUDIT_TRAIL` table (21 CFR 11.10(e) gap)
  2. `InstrumentFileImporter`: Direct local file system share dependency `C:\\instrument\\` (12-Factor statelessness blocker)
  3. `AdminProperties`: Hardcoded administrative passwords in properties file (security finding)
  4. `SampleRegistration`: Local machine `new Date()` / `System.currentTimeMillis()` time calls (cloud time synchronization gap)
  5. `LegacyExcelExporter`: Dead code utility class with zero inbound dependencies and zero runtime hits (retire opportunity)
  6. `ResultRepository`: Shared `RESULT` table accessed by both high-criticality review and low-criticality reporting (DB coupling blocker)

---

## 2. Spring PetClinic (Microservices Reference)
- **Domain:** Healthcare / Veterinary clinic management
- **Stack:** Java 17, Spring Boot 2.x
- **Decomposition Ground Truth:** Multi-service reference architecture (vets, visits, customers, billing).
- **Purpose in ModernRx:** Verifies that ModernRx structural + semantic clustering recovers canonical service boundaries when GxP constraints are neutral.

---

## 3. OpenClinic GA (Open-source Hospital & Clinical Information System)
- **Domain:** Clinical care, laboratory results, pharmacy dispensing
- **Stack:** Java, Servlet/JSP, SQL backend
- **GxP Dimensions:** Regulated patient health records, drug prescription validation, dispensing audit logs.
- **Purpose in ModernRx:** Demonstrates scalability of Engine 2 (GxP Scanner) and Engine 4 (Blast Radius Decomposition) on large-scale clinical monoliths with over 50k LOC.
