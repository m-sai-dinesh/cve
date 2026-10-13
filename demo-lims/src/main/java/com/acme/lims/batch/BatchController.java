package com.acme.lims.batch;

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
@RequestMapping("/batches")
public class BatchController {

    private final BatchReleaseService batchReleaseService;

    @Autowired
    public BatchController(BatchReleaseService batchReleaseService) {
        this.batchReleaseService = batchReleaseService;
    }

    @GetMapping("/disposition")
    public String disposition(Model model) {
        model.addAttribute("batches", batchReleaseService.findAwaitingDisposition());
        return "batch/disposition";
    }

    @GetMapping("/readiness")
    public String readiness(@RequestParam("batchId") long batchId, Model model) {
        model.addAttribute("check", batchReleaseService.evaluateReleaseReadiness(batchId));
        model.addAttribute("batch", batchReleaseService.findById(batchId));
        return "batch/readiness";
    }

    @PreAuthorize("hasRole('QP')")
    @PostMapping("/release")
    public String release(@RequestParam("batchId") long batchId,
                          @RequestParam("password") String password,
                          HttpSession session) {
        String qp = (String) session.getAttribute("currentUser");
        batchReleaseService.releaseBatch(batchId, qp, password);
        return "redirect:/batches/disposition";
    }

    @PreAuthorize("hasRole('QP')")
    @PostMapping("/reject")
    public String reject(@RequestParam("batchId") long batchId,
                         @RequestParam("password") String password,
                         @RequestParam("reason") String reason,
                         HttpSession session) {
        String qp = (String) session.getAttribute("currentUser");
        batchReleaseService.rejectBatch(batchId, qp, password, reason);
        return "redirect:/batches/disposition";
    }
}
