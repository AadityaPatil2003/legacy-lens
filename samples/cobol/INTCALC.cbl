      *================================================================*
      * INTCALC - NIGHTLY BATCH INTEREST CALCULATION (SYNTHETIC)       *
      * READS CUSTOMER MASTER, APPLIES MONTHLY INTEREST TO BALANCES,   *
      * WRITES UPDATED MASTER AND AN EXCEPTION REPORT.                 *
      * WRITTEN FOR THE LEGACYLENS DEMO. NOT TAKEN FROM ANY REAL SYSTEM*
      *================================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTCALC.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUST-IN   ASSIGN TO CUSTIN
               ORGANIZATION IS SEQUENTIAL.
           SELECT CUST-OUT  ASSIGN TO CUSTOUT
               ORGANIZATION IS SEQUENTIAL.
           SELECT EXCP-RPT  ASSIGN TO EXCPRPT.
       DATA DIVISION.
       FILE SECTION.
       FD  CUST-IN.
       COPY CUSTREC.
       FD  CUST-OUT.
       01  CUST-OUT-REC                PIC X(200).
       FD  EXCP-RPT.
       01  EXCP-LINE                   PIC X(132).
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
           88  END-OF-FILE                   VALUE 'Y'.
       01  WS-RATE-RETAIL              PIC V9(4) VALUE .0125.
       01  WS-RATE-BUSINESS            PIC V9(4) VALUE .0095.
       01  WS-INTEREST                 PIC S9(7)V99 COMP-3.
       01  WS-READ-COUNT               PIC 9(7) VALUE 0.
       01  WS-EXCP-COUNT               PIC 9(7) VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2000-PROCESS UNTIL END-OF-FILE
           PERFORM 8000-FINISH
           STOP RUN.

       1000-INIT.
           OPEN INPUT CUST-IN
                OUTPUT CUST-OUT EXCP-RPT
           PERFORM 1100-READ-NEXT.

       1100-READ-NEXT.
           READ CUST-IN
               AT END SET END-OF-FILE TO TRUE
               NOT AT END ADD 1 TO WS-READ-COUNT
           END-READ.

       2000-PROCESS.
           IF CUST-ACTIVE AND CUST-BALANCE > 0
               PERFORM 2100-APPLY-INTEREST
           END-IF
           IF CUST-BALANCE > CUST-CREDIT-LIMIT
               PERFORM 2200-WRITE-EXCEPTION
           END-IF
           WRITE CUST-OUT-REC FROM CUSTOMER-RECORD
           PERFORM 1100-READ-NEXT.

       2100-APPLY-INTEREST.
           IF CUST-BUSINESS
               COMPUTE WS-INTEREST ROUNDED =
                   CUST-BALANCE * WS-RATE-BUSINESS
           ELSE
               COMPUTE WS-INTEREST ROUNDED =
                   CUST-BALANCE * WS-RATE-RETAIL
           END-IF
           ADD WS-INTEREST TO CUST-BALANCE
           MOVE WS-INTEREST TO CUST-LAST-TXN-AMT.

       2200-WRITE-EXCEPTION.
           ADD 1 TO WS-EXCP-COUNT
           MOVE SPACES TO EXCP-LINE
           STRING 'OVER LIMIT: ' CUST-ID DELIMITED BY SIZE
               INTO EXCP-LINE
           WRITE EXCP-LINE.

       8000-FINISH.
           CALL 'AUDITLOG' USING WS-READ-COUNT WS-EXCP-COUNT
           CLOSE CUST-IN CUST-OUT EXCP-RPT.
