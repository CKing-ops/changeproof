       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYSCRN.
      * Synthetic outgoing payment screening.
      * Bank: {bank}
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LIMIT                PIC S9(9)V99 COMP-3.
       01  WS-TOTAL                PIC S9(9)V99 COMP-3.
       LINKAGE SECTION.
       01  LK-AMOUNT               PIC S9(9)V99 COMP-3.
       01  LK-CURRENCY             PIC X(3).
       01  LK-DAILY-USED           PIC S9(9)V99 COMP-3.
       01  LK-CHANNEL              PIC X.
           88  CH-ONLINE           VALUE 'O'.
           88  CH-BRANCH           VALUE 'B'.
       01  LK-DECISION             PIC X(8).
       01  LK-REPORT               PIC X.
       PROCEDURE DIVISION USING LK-AMOUNT LK-CURRENCY LK-DAILY-USED
                                LK-CHANNEL LK-DECISION LK-REPORT.
       MAIN-PARA.
           MOVE 'APPROVE' TO LK-DECISION
           MOVE 'N' TO LK-REPORT
           IF LK-CURRENCY NOT = '{currency}'
               MOVE 'FXREVIEW' TO LK-DECISION
               GOBACK
           END-IF
           IF LK-AMOUNT <= 0
               MOVE 'INVALID' TO LK-DECISION
               GOBACK
           END-IF
           IF CH-ONLINE
               MOVE {online_limit} TO WS-LIMIT
           ELSE
               MOVE {branch_limit} TO WS-LIMIT
           END-IF
           COMPUTE WS-TOTAL = LK-DAILY-USED + LK-AMOUNT
           IF WS-TOTAL > WS-LIMIT
               MOVE 'DECLINE' TO LK-DECISION
           END-IF
           IF LK-AMOUNT >= {report_threshold}
               MOVE 'Y' TO LK-REPORT
           END-IF
           GOBACK.
