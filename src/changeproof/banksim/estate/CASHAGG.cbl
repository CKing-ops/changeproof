       IDENTIFICATION DIVISION.
       PROGRAM-ID. CASHAGG.
      * Synthetic cash transaction monitoring: a customer's cash
      * in or out is totalled over the business day.
      * Bank: {bank}
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CASH-TOTAL           PIC S9(9)V99 COMP-3.
       LINKAGE SECTION.
       01  LK-AMOUNT               PIC S9(7)V99 COMP-3.
       01  LK-KIND                 PIC X.
           88  KIND-CASH-IN        VALUE 'I'.
           88  KIND-CASH-OUT       VALUE 'O'.
           88  KIND-CHEQUE         VALUE 'Q'.
       01  LK-CASH-TODAY           PIC S9(9)V99 COMP-3.
       01  LK-REPORT               PIC X.
       01  LK-ALERT                PIC X(8).
       PROCEDURE DIVISION USING LK-AMOUNT LK-KIND LK-CASH-TODAY
                                LK-REPORT LK-ALERT.
       MAIN-PARA.
           MOVE 'N' TO LK-REPORT
           MOVE SPACES TO LK-ALERT
           MOVE LK-CASH-TODAY TO WS-CASH-TOTAL
           IF KIND-CASH-IN OR KIND-CASH-OUT
               ADD LK-AMOUNT TO WS-CASH-TOTAL
           END-IF
           IF WS-CASH-TOTAL {cash_op} {cash_threshold}
               MOVE 'Y' TO LK-REPORT
           END-IF
           IF KIND-CASH-IN AND LK-CASH-TODAY > 0
              AND LK-AMOUNT >= {structuring_floor}
              AND LK-AMOUNT < {cash_threshold}
               MOVE 'STRUCT' TO LK-ALERT
           END-IF
           GOBACK.
