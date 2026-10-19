       IDENTIFICATION DIVISION.
       PROGRAM-ID. FEEASSES.
      * Synthetic monthly account fee.
      * Bank: {bank}
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-AVG-BALANCE          PIC S9(9)V99 COMP-3.
       01  LK-TXN-COUNT            PIC 9(4) COMP.
       01  LK-SEGMENT              PIC X.
           88  SEG-RETAIL          VALUE 'R'.
           88  SEG-BUSINESS        VALUE 'B'.
           88  SEG-STUDENT         VALUE 'S'.
       01  LK-FEE                  PIC S9(5)V99 COMP-3.
       01  LK-WAIVED               PIC X.
       PROCEDURE DIVISION USING LK-AVG-BALANCE LK-TXN-COUNT LK-SEGMENT
                                LK-FEE LK-WAIVED.
       MAIN-PARA.
           MOVE 0 TO LK-FEE
           MOVE 'N' TO LK-WAIVED
           EVALUATE TRUE
               WHEN SEG-STUDENT
                   MOVE 'Y' TO LK-WAIVED
               WHEN SEG-RETAIL
                   IF LK-AVG-BALANCE >= {retail_minimum}
                       MOVE 'Y' TO LK-WAIVED
                   ELSE
                       MOVE {retail_fee} TO LK-FEE
                   END-IF
               WHEN SEG-BUSINESS
                   MOVE {business_fee} TO LK-FEE
                   IF LK-TXN-COUNT > {free_txns}
                       COMPUTE LK-FEE = LK-FEE +
                           (LK-TXN-COUNT - {free_txns}) * {per_txn}
                   END-IF
               WHEN OTHER
                   MOVE 'E' TO LK-WAIVED
           END-EVALUATE
           GOBACK.
