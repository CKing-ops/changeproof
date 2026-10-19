       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYCALC.
      * Synthetic subprogram: packed and binary amounts, a rate table
      * and a date read through a redefinition.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-GROSS                PIC S9(7)V99 COMP-3.
       01  LK-HOURS                PIC S9(4) COMP.
       01  LK-RATES.
           05  LK-RATE             PIC 9V999 OCCURS 3 TIMES.
       01  LK-BAND                 PIC 9.
       01  LK-WHEN.
           05  LK-DATE             PIC X(8).
           05  LK-DATE-PARTS REDEFINES LK-DATE.
               10  LK-YEAR         PIC 9(4).
               10  LK-MONTH        PIC 99.
               10  LK-DAY          PIC 99.
       01  LK-NET                  PIC S9(7)V99 COMP-3.
       01  LK-FLAG                 PIC X.
       PROCEDURE DIVISION USING LK-GROSS LK-HOURS LK-RATES LK-BAND
                                LK-WHEN LK-NET LK-FLAG.
       MAIN-PARA.
           MOVE 'N' TO LK-FLAG
           IF LK-BAND < 1 OR LK-BAND > 3
               MOVE 'B' TO LK-FLAG
               MOVE 0 TO LK-NET
               GOBACK
           END-IF
           COMPUTE LK-NET ROUNDED = LK-GROSS * (1 - LK-RATE (LK-BAND))
           IF LK-HOURS > 160
               ADD 50 TO LK-NET
               MOVE 'O' TO LK-FLAG
           END-IF
           IF LK-MONTH = 12
               ADD 100 TO LK-NET
               MOVE 'X' TO LK-FLAG
           END-IF
           GOBACK.
