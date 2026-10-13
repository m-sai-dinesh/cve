package com.acme.lims.util;

public final class StringHelper {

    private StringHelper() {
    }

    public static boolean isBlank(String s) {
        return s == null || s.trim().length() == 0;
    }

    public static String nvl(String s, String fallback) {
        return isBlank(s) ? fallback : s;
    }

    public static String truncate(String s, int max) {
        if (s == null) {
            return null;
        }
        return s.length() <= max ? s : s.substring(0, max);
    }

    public static String padLeft(String s, int width, char pad) {
        if (s == null) {
            s = "";
        }
        StringBuilder sb = new StringBuilder();
        for (int i = s.length(); i < width; i++) {
            sb.append(pad);
        }
        return sb.append(s).toString();
    }

    public static String join(String[] parts, String sep) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            if (i > 0) {
                sb.append(sep);
            }
            sb.append(parts[i]);
        }
        return sb.toString();
    }
}
