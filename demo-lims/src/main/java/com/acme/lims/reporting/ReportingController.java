package com.acme.lims.reporting;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
@RequestMapping("/reports")
public class ReportingController {

    private final CoaReportService coaReportService;

    @Autowired
    public ReportingController(CoaReportService coaReportService) {
        this.coaReportService = coaReportService;
    }

    @GetMapping("/coa")
    public String coa(@RequestParam("batchId") long batchId, Model model) {
        model.addAttribute("rows", coaReportService.buildCoaData(batchId));
        return "reporting/coa";
    }

    @GetMapping("/trend")
    public String trend(@RequestParam("productCode") String productCode,
                        @RequestParam("analyte") String analyte, Model model) {
        model.addAttribute("rows", coaReportService.buildTrendData(productCode, analyte));
        return "reporting/trend";
    }

    @GetMapping("/oos")
    public String oos(Model model) {
        model.addAttribute("rows", coaReportService.buildOosSummary());
        return "reporting/oos";
    }

    @GetMapping("/backlog")
    public String backlog(Model model) {
        model.addAttribute("rows", coaReportService.buildReviewBacklog());
        return "reporting/backlog";
    }
}
