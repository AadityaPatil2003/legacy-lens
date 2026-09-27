      *================================================================*
      * ACCTINQ - CICS ONLINE CUSTOMER ACCOUNT INQUIRY (SYNTHETIC)     *
      * TRANSACTION AINQ. SHOWS MAP ACCTMAP, READS CUSTMAST VSAM FILE. *
      * WRITTEN FOR THE LEGACYLENS DEMO. NOT TAKEN FROM ANY REAL SYSTEM*
      *================================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTINQ.
       AUTHOR. LEGACYLENS-DEMO.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RESP                     PIC S9(8) COMP.
       01  WS-CUST-KEY                 PIC 9(8).
       01  WS-MESSAGE                  PIC X(60).
       01  WS-AVAILABLE                PIC S9(7)V99 COMP-3.
       COPY CUSTREC.
       COPY ACCTMAP.
       LINKAGE SECTION.
       01  DFHCOMMAREA                 PIC X(8).
       PROCEDURE DIVISION.
       0000-MAIN.
           IF EIBCALEN = 0
               PERFORM 1000-SEND-EMPTY-MAP
           ELSE
               PERFORM 2000-PROCESS-INPUT
           END-IF
           EXEC CICS RETURN
               TRANSID('AINQ')
               COMMAREA(WS-CUST-KEY)
           END-EXEC.

       1000-SEND-EMPTY-MAP.
           MOVE LOW-VALUES TO ACCTMAPO
           MOVE 'ENTER CUSTOMER ID AND PRESS ENTER' TO MSGO
           EXEC CICS SEND MAP('ACCTMAP') MAPSET('ACCTSET')
               FROM(ACCTMAPO) ERASE
           END-EXEC.

       2000-PROCESS-INPUT.
           EXEC CICS RECEIVE MAP('ACCTMAP') MAPSET('ACCTSET')
               INTO(ACCTMAPI) RESP(WS-RESP)
           END-EXEC
           IF CUSTIDI NOT NUMERIC
               MOVE 'CUSTOMER ID MUST BE NUMERIC' TO WS-MESSAGE
               PERFORM 9000-SEND-ERROR
           ELSE
               MOVE CUSTIDI TO WS-CUST-KEY
               PERFORM 3000-READ-CUSTOMER
           END-IF.

       3000-READ-CUSTOMER.
           EXEC CICS READ FILE('CUSTMAST')
               INTO(CUSTOMER-RECORD)
               RIDFLD(WS-CUST-KEY)
               RESP(WS-RESP)
           END-EXEC
           EVALUATE WS-RESP
               WHEN DFHRESP(NORMAL)
                   PERFORM 4000-CHECK-STATUS
               WHEN DFHRESP(NOTFND)
                   MOVE 'CUSTOMER NOT FOUND' TO WS-MESSAGE
                   PERFORM 9000-SEND-ERROR
               WHEN OTHER
                   EXEC CICS LINK PROGRAM('ERRLOG')
                       COMMAREA(WS-RESP)
                   END-EXEC
                   MOVE 'SYSTEM ERROR - CONTACT SUPPORT' TO WS-MESSAGE
                   PERFORM 9000-SEND-ERROR
           END-EVALUATE.

       4000-CHECK-STATUS.
           IF CUST-CLOSED
               MOVE 'ACCOUNT IS CLOSED' TO WS-MESSAGE
               PERFORM 9000-SEND-ERROR
           ELSE
               COMPUTE WS-AVAILABLE =
                   CUST-CREDIT-LIMIT - CUST-BALANCE
               IF WS-AVAILABLE < 0
                   MOVE 'OVER LIMIT - REFER TO LENDING' TO WS-MESSAGE
               ELSE
                   MOVE SPACES TO WS-MESSAGE
               END-IF
               PERFORM 5000-SEND-DETAIL
           END-IF.

       5000-SEND-DETAIL.
           MOVE CUST-ID           TO CUSTIDO
           MOVE CUST-LAST-NAME    TO NAMEO
           MOVE CUST-BALANCE      TO BALO
           MOVE WS-AVAILABLE      TO AVAILO
           MOVE WS-MESSAGE        TO MSGO
           EXEC CICS SEND MAP('ACCTMAP') MAPSET('ACCTSET')
               FROM(ACCTMAPO) DATAONLY
           END-EXEC.

       9000-SEND-ERROR.
           MOVE WS-MESSAGE TO MSGO
           EXEC CICS SEND MAP('ACCTMAP') MAPSET('ACCTSET')
               FROM(ACCTMAPO) DATAONLY ALARM
           END-EXEC.
