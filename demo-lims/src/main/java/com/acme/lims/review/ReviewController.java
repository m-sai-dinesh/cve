package com.acme.lims.review;

import javax.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
@RequestMapping("/review")
public class ReviewController {

    private final ReviewService reviewService;

    @Autowired
    public ReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @GetMapping("/signatures")
    public String signatures(@RequestParam("resultId") long resultId, Model model) {
        model.addAttribute("signatures", reviewService.findSignatures(resultId));
        return "review/signatures";
    }

    @PreAuthorize("hasRole('REVIEWER')")
    @PostMapping("/approve")
    public String approve(@RequestParam("resultId") long resultId,
                          @RequestParam("password") String password,
                          @RequestParam("meaning") String meaning,
                          HttpSession session) {
        String user = (String) session.getAttribute("currentUser");
        reviewService.approveResult(resultId, user, password, meaning);
        return "redirect:/results/queue";
    }

    @PreAuthorize("hasRole('REVIEWER')")
    @PostMapping("/reject")
    public String reject(@RequestParam("resultId") long resultId,
                         @RequestParam("password") String password,
                         @RequestParam("reason") String reason,
                         HttpSession session) {
        String user = (String) session.getAttribute("currentUser");
        reviewService.rejectResult(resultId, user, password, reason);
        return "redirect:/results/queue";
    }
}
