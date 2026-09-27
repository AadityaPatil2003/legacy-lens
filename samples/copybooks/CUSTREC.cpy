      *================================================================*
      * CUSTREC  - CUSTOMER MASTER RECORD (SYNTHETIC SAMPLE DATA)      *
      * WRITTEN FOR THE LEGACYLENS DEMO. NOT TAKEN FROM ANY REAL SYSTEM*
      *================================================================*
       01  CUSTOMER-RECORD.
           05  CUST-ID                 PIC 9(8).
           05  CUST-NAME.
               10  CUST-FIRST-NAME     PIC X(20).
               10  CUST-LAST-NAME      PIC X(25).
           05  CUST-TYPE               PIC X(1).
               88  CUST-RETAIL                   VALUE 'R'.
               88  CUST-BUSINESS                 VALUE 'B'.
           05  CUST-STATUS             PIC X(1).
               88  CUST-ACTIVE                   VALUE 'A'.
               88  CUST-CLOSED                   VALUE 'C'.
           05  CUST-OPEN-DATE          PIC 9(8).
           05  CUST-CREDIT-LIMIT       PIC S9(7)V99 COMP-3.
           05  CUST-BALANCE            PIC S9(7)V99 COMP-3.
           05  CUST-PHONE-COUNT        PIC 9(1).
           05  CUST-PHONE              PIC X(12) OCCURS 3 TIMES.
           05  CUST-ADDRESS.
               10  CUST-STREET         PIC X(30).
               10  CUST-SUBURB         PIC X(20).
               10  CUST-STATE          PIC X(3).
               10  CUST-POSTCODE       PIC 9(4).
           05  CUST-ADDRESS-ALT REDEFINES CUST-ADDRESS
                                       PIC X(57).
           05  CUST-LAST-TXN-AMT       PIC S9(5)V99 COMP-3.
           05  FILLER                  PIC X(10).
