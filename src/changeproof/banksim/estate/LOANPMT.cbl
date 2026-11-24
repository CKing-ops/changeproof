       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOANPMT.
      * Synthetic monthly loan installment and late fee.
      * Bank: {bank}
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-APR                  PIC 9V9(6) COMP-3.
       LINKAGE SECTION.
       01  LK-PRINCIPAL            PIC S9(9)V99 COMP-3.
       01  LK-PAYMENT              PIC S9(7)V99 COMP-3.
       01  LK-DAYS-LATE            PIC 9(3).
       01  LK-LOAN-TYPE            PIC X.
           88  LOAN-MORTGAGE       VALUE 'M'.
           88  LOAN-AUTO           VALUE 'A'.
           88  LOAN-PERSONAL       VALUE 'P'.
       01  LK-INTEREST             PIC S9(7)V99 COMP-3.
       01  LK-TO-PRINCIPAL         PIC S9(7)V99 COMP-3.
       01  LK-LATE-FEE             PIC S9(5)V99 COMP-3.
       01  LK-STATUS               PIC X(8).
       PROCEDURE DIVISION USING LK-PRINCIPAL LK-PAYMENT LK-DAYS-LATE
                                LK-LOAN-TYPE LK-INTEREST
                                LK-TO-PRINCIPAL LK-LATE-FEE LK-STATUS.
       MAIN-PARA.
           MOVE 0 TO LK-INTEREST LK-TO-PRINCIPAL LK-LATE-FEE
           MOVE 'CURRENT' TO LK-STATUS
           EVALUATE TRUE
               WHEN LOAN-MORTGAGE
                   MOVE {apr_mortgage} TO WS-APR
               WHEN LOAN-AUTO
                   MOVE {apr_auto} TO WS-APR
               WHEN LOAN-PERSONAL
                   MOVE {apr_personal} TO WS-APR
               WHEN OTHER
                   MOVE 'BADLOAN' TO LK-STATUS
                   GOBACK
           END-EVALUATE
           COMPUTE LK-INTEREST ROUNDED =
               LK-PRINCIPAL * WS-APR / 12
           COMPUTE LK-TO-PRINCIPAL = LK-PAYMENT - LK-INTEREST
           IF LK-TO-PRINCIPAL < 0
               MOVE 'NEGAM' TO LK-STATUS
           END-IF
           IF LK-DAYS-LATE > {grace_days}
               COMPUTE LK-LATE-FEE ROUNDED =
                   LK-PAYMENT * {late_pct}
               IF LK-LATE-FEE < {late_min}
                   MOVE {late_min} TO LK-LATE-FEE
               END-IF
               IF LK-LATE-FEE > {late_cap}
                   MOVE {late_cap} TO LK-LATE-FEE
               END-IF
               MOVE 'LATE' TO LK-STATUS
           END-IF
           IF LK-DAYS-LATE >= {delinquent_days}
               MOVE 'DELINQ' TO LK-STATUS
           END-IF
           GOBACK.
