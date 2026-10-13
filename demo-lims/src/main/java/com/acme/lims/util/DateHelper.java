package com.acme.lims.util;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;

public final class DateHelper {

    // SimpleDateFormat is not thread-safe; sharing a static instance across
    // request threads can silently corrupt formatted GxP timestamps.
    private static final SimpleDateFormat LONG_FORMAT = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
    private static final SimpleDateFormat SHORT_FORMAT = new SimpleDateFormat("yyyy-MM-dd");

    private DateHelper() {
    }

    public static String formatLong(Date d) {
        return d == null ? "" : LONG_FORMAT.format(d);
    }

    public static String formatShort(Date d) {
        return d == null ? "" : SHORT_FORMAT.format(d);
    }

    public static Date now() {
        return new Date();
    }

    public static Date addDays(Date base, int days) {
        Calendar c = Calendar.getInstance();
        c.setTime(base);
        c.add(Calendar.DAY_OF_MONTH, days);
        return c.getTime();
    }

    public static boolean isSameDay(Date a, Date b) {
        return formatShort(a).equals(formatShort(b));
    }
}
