package com.example.pay.report;

import com.example.pay.core.Ledger;

/** Synthetic: end-of-day totals. */
public class DailyReport {
    private final Ledger ledger;

    public DailyReport(Ledger ledger) {
        this.ledger = ledger;
    }

    public String render() {
        return "TOTAL " + ledger.total();
    }
}
