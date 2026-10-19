       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTACCR.
      * Synthetic deposit interest accrual.
      * Bank: {bank}
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RATE                 PIC 9V9(6) COMP-3.
       LINKAGE SECTION.
       01  LK-BALANCE              PIC S9(9)V99 COMP-3.
       01  LK-DAYS                 PIC 9(3).
       01  LK-PRODUCT              PIC X.
           88  PROD-SAVINGS        VALUE 'S'.
           88  PROD-CHECKING       VALUE 'C'.
       01  LK-INTEREST             PIC S9(7)V99 COMP-3.
       01  LK-STATUS               PIC X(8).
       PROCEDURE DIVISION USING LK-BALANCE LK-DAYS LK-PRODUCT
                                LK-INTEREST LK-STATUS.
       MAIN-PARA.
           MOVE 0 TO LK-INTEREST
           MOVE SPACES TO LK-STATUS
           IF LK-BALANCE <= 0
               MOVE 'NOACCRUE' TO LK-STATUS
               GOBACK
           END-IF
           EVALUATE TRUE
               WHEN PROD-SAVINGS
                   IF LK-BALANCE >= {tier}
                       MOVE {rate_high} TO WS-RATE
                   ELSE
                       MOVE {rate_low} TO WS-RATE
                   END-IF
               WHEN PROD-CHECKING
                   MOVE {rate_checking} TO WS-RATE
               WHEN OTHER
                   MOVE 'BADPROD' TO LK-STATUS
                   GOBACK
           END-EVALUATE
           COMPUTE LK-INTEREST ROUNDED =
               LK-BALANCE * WS-RATE * LK-DAYS / {basis}
           IF LK-DAYS > {max_days}
               MOVE 'LONGPRD' TO LK-STATUS
           END-IF
           GOBACK.
