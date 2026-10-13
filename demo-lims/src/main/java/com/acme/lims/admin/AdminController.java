package com.acme.lims.admin;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

import javax.servlet.http.HttpSession;

@Controller
@RequestMapping("/admin")
public class AdminController {

    private final UserAdminService userAdminService;

    @Autowired
    public AdminController(UserAdminService userAdminService) {
        this.userAdminService = userAdminService;
    }

    @PreAuthorize("hasRole('ADMIN')")
    @GetMapping("/users")
    public String users(Model model) {
        model.addAttribute("users", userAdminService.listActiveUsers());
        return "admin/users";
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PostMapping("/users/create")
    public String create(@RequestParam("username") String username,
                         @RequestParam("fullName") String fullName,
                         @RequestParam("password") String password,
                         HttpSession session) {
        String by = (String) session.getAttribute("currentUser");
        userAdminService.createUser(username, fullName, password, by);
        return "redirect:/admin/users";
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PostMapping("/users/role")
    public String assignRole(@RequestParam("userId") long userId,
                             @RequestParam("role") String role,
                             HttpSession session) {
        String by = (String) session.getAttribute("currentUser");
        userAdminService.assignRole(userId, role, by);
        return "redirect:/admin/users";
    }
}
