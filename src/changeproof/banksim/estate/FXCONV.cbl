       IDENTIFICATION DIVISION.
       PROGRAM-ID. FXCONV.
      * Synthetic foreign currency conversion into {currency}.
      * Bank: {bank}
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RATE                 PIC 9(3)V9(6) COMP-3.
       LINKAGE SECTION.
       01  LK-AMOUNT               PIC S9(9)V99 COMP-3.
       01  LK-FROM-CCY             PIC X(3).
       01  LK-CUSTOMER             PIC X.
           88  CUST-PREMIER        VALUE 'P'.
       01  LK-CONVERTED            PIC S9(9)V99 COMP-3.
       01  LK-FX-FEE               PIC S9(5)V99 COMP-3.
       01  LK-DECISION             PIC X(8).
       PROCEDURE DIVISION USING LK-AMOUNT LK-FROM-CCY LK-CUSTOMER
                                LK-CONVERTED LK-FX-FEE LK-DECISION.
       MAIN-PARA.
           MOVE 0 TO LK-CONVERTED LK-FX-FEE
           MOVE 'BOOKED' TO LK-DECISION
           EVALUATE LK-FROM-CCY
               WHEN '{fx1}'
                   MOVE {fx1_rate} TO WS-RATE
               WHEN '{fx2}'
                   MOVE {fx2_rate} TO WS-RATE
               WHEN '{fx3}'
                   MOVE {fx3_rate} TO WS-RATE
               WHEN OTHER
                   MOVE 'NORATE' TO LK-DECISION
                   GOBACK
           END-EVALUATE
           IF LK-AMOUNT <= 0
               MOVE 'INVALID' TO LK-DECISION
               GOBACK
           END-IF
           COMPUTE LK-CONVERTED ROUNDED = LK-AMOUNT * WS-RATE
           IF NOT CUST-PREMIER
               COMPUTE LK-FX-FEE ROUNDED =
                   LK-CONVERTED * {fx_spread}
               IF LK-FX-FEE < {fx_min_fee}
                   MOVE {fx_min_fee} TO LK-FX-FEE
               END-IF
           END-IF
           IF LK-CONVERTED >= {fx_review}
               MOVE 'REVIEW' TO LK-DECISION
           END-IF
           GOBACK.
