package com.acme.lims.result;

import java.math.BigDecimal;

import javax.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
@RequestMapping("/results")
public class ResultController {

    private final ResultService resultService;

    @Autowired
    public ResultController(ResultService resultService) {
        this.resultService = resultService;
    }

    @GetMapping("/queue")
    public String queue(Model model) {
        model.addAttribute("results", resultService.findAwaitingReview());
        return "result/queue";
    }

    @GetMapping("/sample")
    public String bySample(@RequestParam("sampleId") long sampleId, Model model) {
        model.addAttribute("results", resultService.findBySample(sampleId));
        return "result/list";
    }

    @PostMapping("/enter")
    public String enter(@RequestParam("sampleId") long sampleId,
                        @RequestParam("analyte") String analyte,
                        @RequestParam("value") BigDecimal value,
                        @RequestParam("unit") String unit,
                        @RequestParam("instrumentId") String instrumentId,
                        HttpSession session) {
        String user = (String) session.getAttribute("currentUser");
        resultService.enterResult(sampleId, analyte, value, unit, instrumentId, user);
        return "redirect:/results/sample?sampleId=" + sampleId;
    }

    @PostMapping("/correct")
    public String correct(@RequestParam("resultId") long resultId,
                          @RequestParam("value") BigDecimal value,
                          HttpSession session) {
        String user = (String) session.getAttribute("currentUser");
        resultService.correctResult(resultId, value, user);
        return "redirect:/results/queue";
    }
}
