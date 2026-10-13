package com.acme.lims.admin;

import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;

/**
 * User and role administration.
 *
 * SECURITY FINDING: a shared administrator account with its password in
 * application.properties bypasses per-user attributability, which Part 11
 * §11.10(d)/(g) and ALCOA++ "Attributable" both require.
 */
@Service
public class UserAdminService {

    private final JdbcTemplate jdbc;
    private final PasswordEncoder passwordEncoder;
    private final AuditService auditService;

    @Value("${lims.admin.username}")
    private String adminUsername;

    @Value("${lims.admin.password}")
    private String adminPassword;

    @Autowired
    public UserAdminService(DataSource dataSource, PasswordEncoder passwordEncoder,
                            AuditService auditService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.passwordEncoder = passwordEncoder;
        this.auditService = auditService;
    }

    /**
     * Break-glass login used by support. Compares against the configured
     * password in plain text.
     */
    public boolean authenticateAdmin(String username, String password) {
        return adminUsername.equals(username) && adminPassword.equals(password);
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public long createUser(String username, String fullName, String rawPassword, String createdBy) {
        long userId = System.currentTimeMillis() % 100000000L;
        jdbc.update(
            "INSERT INTO LIMS_USER (USER_ID, USERNAME, FULL_NAME, PASSWORD_HASH, ACTIVE_FLAG) "
          + "VALUES (?, ?, ?, ?, 'Y')",
            userId, username, fullName, passwordEncoder.encode(rawPassword));
        auditService.recordCreation("LIMS_USER", username, createdBy);
        return userId;
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void assignRole(long userId, String roleName, String assignedBy) {
        jdbc.update(
            "INSERT INTO USER_ROLE (USER_ID, ROLE_ID) "
          + "SELECT ?, ROLE_ID FROM LIMS_ROLE WHERE ROLE_NAME = ?",
            userId, roleName);
        auditService.recordChange("USER_ROLE", String.valueOf(userId), "ROLE",
            null, roleName, assignedBy, "INSERT");
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void deactivateUser(long userId, String deactivatedBy) {
        jdbc.update("UPDATE LIMS_USER SET ACTIVE_FLAG = 'N' WHERE USER_ID = ?", userId);
        auditService.recordChange("LIMS_USER", String.valueOf(userId), "ACTIVE_FLAG",
            "Y", "N", deactivatedBy, "UPDATE");
    }

    public List<String> listRolesFor(String username) {
        return jdbc.queryForList(
            "SELECT R.ROLE_NAME FROM LIMS_ROLE R "
          + "JOIN USER_ROLE UR ON UR.ROLE_ID = R.ROLE_ID "
          + "JOIN LIMS_USER U ON U.USER_ID = UR.USER_ID WHERE U.USERNAME = ?",
            String.class, username);
    }

    public List<String> listActiveUsers() {
        return jdbc.queryForList(
            "SELECT USERNAME FROM LIMS_USER WHERE ACTIVE_FLAG = 'Y' ORDER BY USERNAME", String.class);
    }
}
