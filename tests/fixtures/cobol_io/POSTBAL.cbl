       IDENTIFICATION DIVISION.
       PROGRAM-ID. POSTBAL.
      * Synthetic batch job: posts daily transactions to account
      * balances and writes rejected transactions to a file.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRAN-FILE ASSIGN TO TRANFILE
                  ORGANIZATION IS SEQUENTIAL
                  FILE STATUS IS WS-TRAN-STATUS.
           SELECT ACCT-FILE ASSIGN TO ACCTFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS RANDOM
                  RECORD KEY IS FD-ACCT-ID
                  FILE STATUS IS WS-ACCT-STATUS.
           SELECT REJECT-FILE ASSIGN TO REJECTS
                  ORGANIZATION IS SEQUENTIAL
                  FILE STATUS IS WS-REJ-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  TRAN-FILE.
       01  FD-TRAN-REC             PIC X(30).
       FD  ACCT-FILE.
       01  FD-ACCT-REC.
           05  FD-ACCT-ID          PIC 9(6).
           05  FD-ACCT-DATA        PIC X(20).
       FD  REJECT-FILE.
       01  FD-REJECT-REC           PIC X(40).
       WORKING-STORAGE SECTION.
       01  WS-TRAN.
           05  TRAN-ACCT-ID        PIC 9(6).
           05  TRAN-TYPE           PIC X.
               88  TRAN-CREDIT     VALUE 'C'.
               88  TRAN-DEBIT      VALUE 'D'.
           05  TRAN-AMOUNT         PIC S9(7)V99 COMP-3.
           05  FILLER              PIC X(18).
       01  WS-ACCOUNT.
           05  ACCT-ID             PIC 9(6).
           05  ACCT-BALANCE        PIC S9(9)V99 COMP-3.
           05  ACCT-LIMIT          PIC S9(7)V99 COMP-3.
           05  FILLER              PIC X(9).
       01  WS-REJECT.
           05  REJ-ACCT-ID         PIC 9(6).
           05  REJ-REASON          PIC X(10).
           05  REJ-DATE            PIC X(8).
           05  FILLER              PIC X(16).
       01  WS-TRAN-STATUS          PIC XX.
       01  WS-ACCT-STATUS          PIC XX.
       01  WS-REJ-STATUS           PIC XX.
       01  WS-EOF                  PIC X VALUE 'N'.
       01  WS-POSTED               PIC 9(5) VALUE 0.
       01  WS-REJECTED             PIC 9(5) VALUE 0.
       01  WS-TODAY                PIC X(8).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE FUNCTION CURRENT-DATE (1:8) TO WS-TODAY
           OPEN INPUT TRAN-FILE
           OPEN I-O ACCT-FILE
           OPEN OUTPUT REJECT-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ TRAN-FILE INTO WS-TRAN
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM POST-TRAN
               END-READ
           END-PERFORM
           DISPLAY 'POSTED ' WS-POSTED ' REJECTED ' WS-REJECTED
           CLOSE TRAN-FILE ACCT-FILE REJECT-FILE
           IF WS-REJECTED > 0
               MOVE 4 TO RETURN-CODE
           END-IF
           STOP RUN.
       POST-TRAN.
           MOVE TRAN-ACCT-ID TO FD-ACCT-ID
           READ ACCT-FILE INTO WS-ACCOUNT
               INVALID KEY
                   MOVE 'NOACCOUNT' TO REJ-REASON
                   PERFORM REJECT-TRAN
               NOT INVALID KEY
                   PERFORM APPLY-TRAN
           END-READ.
       APPLY-TRAN.
           EVALUATE TRUE
               WHEN TRAN-CREDIT
                   ADD TRAN-AMOUNT TO ACCT-BALANCE
                   PERFORM SAVE-ACCOUNT
               WHEN TRAN-DEBIT
                   IF ACCT-BALANCE - TRAN-AMOUNT < 0 - ACCT-LIMIT
                       MOVE 'OVERLIMIT' TO REJ-REASON
                       PERFORM REJECT-TRAN
                   ELSE
                       SUBTRACT TRAN-AMOUNT FROM ACCT-BALANCE
                       PERFORM SAVE-ACCOUNT
                   END-IF
               WHEN OTHER
                   MOVE 'BADTYPE' TO REJ-REASON
                   PERFORM REJECT-TRAN
           END-EVALUATE.
       SAVE-ACCOUNT.
           REWRITE FD-ACCT-REC FROM WS-ACCOUNT
           ADD 1 TO WS-POSTED.
       REJECT-TRAN.
           MOVE TRAN-ACCT-ID TO REJ-ACCT-ID
           MOVE WS-TODAY TO REJ-DATE
           WRITE FD-REJECT-REC FROM WS-REJECT
           ADD 1 TO WS-REJECTED.
