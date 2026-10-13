package com.acme.lims.util;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** JUnit 4 - the only tests in AcmeLIMS, and they cover a utility class. */
public class StringHelperTest {

    @Test
    public void blankDetectsNullAndWhitespace() {
        assertTrue(StringHelper.isBlank(null));
        assertTrue(StringHelper.isBlank("   "));
        assertFalse(StringHelper.isBlank("x"));
    }

    @Test
    public void truncateRespectsMax() {
        assertEquals("abc", StringHelper.truncate("abcdef", 3));
        assertEquals("ab", StringHelper.truncate("ab", 5));
    }

    @Test
    public void joinInsertsSeparator() {
        assertEquals("a|b|c", StringHelper.join(new String[] { "a", "b", "c" }, "|"));
    }
}
