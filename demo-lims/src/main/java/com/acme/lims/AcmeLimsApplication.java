package com.acme.lims;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class AcmeLimsApplication {

    public static void main(String[] args) {
        SpringApplication.run(AcmeLimsApplication.class, args);
    }
}
