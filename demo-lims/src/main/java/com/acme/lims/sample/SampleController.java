package com.acme.lims.sample;

import javax.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
@RequestMapping("/samples")
public class SampleController {

    private final SampleService sampleService;

    @Autowired
    public SampleController(SampleService sampleService) {
        this.sampleService = sampleService;
    }

    @GetMapping("/pending")
    public String pending(Model model) {
        model.addAttribute("samples", sampleService.findPending());
        return "sample/pending";
    }

    @GetMapping("/{id}")
    public String detail(@RequestParam("id") long id, Model model) {
        model.addAttribute("sample", sampleService.findById(id));
        return "sample/detail";
    }

    @PostMapping("/register")
    public String register(@RequestParam("sampleCode") String sampleCode,
                           @RequestParam("productCode") String productCode,
                           @RequestParam("batchId") Long batchId,
                           @RequestParam("matrix") String matrix,
                           HttpSession session) {
        // Operator identity is read out of the servlet session (not stateless).
        String user = (String) session.getAttribute("currentUser");
        long id = sampleService.registerSample(sampleCode, productCode, batchId, matrix, user);
        session.setAttribute("lastRegisteredSample", Long.valueOf(id));
        return "redirect:/samples/pending";
    }

    @PostMapping("/custody")
    public String moveCustody(@RequestParam("sampleId") long sampleId,
                              @RequestParam("to") String toLocation,
                              HttpSession session) {
        String user = (String) session.getAttribute("currentUser");
        sampleService.recordCustody(sampleId, "SAMPLE_STORE", toLocation, user);
        return "redirect:/samples/" + sampleId;
    }
}
