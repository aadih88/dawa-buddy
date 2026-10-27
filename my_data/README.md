# my_data  (private - ignored by git)

Put your real prescription and bill here. Nothing in this folder is ever committed.

Redact before you start: patient name, phone, address, UHID/bill number, doctor registration number.
Keep: medicine names, strengths, quantities, rates, amounts, dates are not needed.

## rx.txt  - type each prescription line as written
    Tab Telma 40 1-0-0 x 30 days
    Dolo 650 SOS

## bill.txt - one line per item:  description | qty | rate | amount | unit | pack
    TELMA 40 | 3 | 124.00 | 372.00 | strip | 10      (rate printed per strip of 10)
    DOLO 650 | 10 | 2.10 | 21.00 | tab                (rate printed per tablet)
    IV SET DISPOSABLE | 4 | 85.00 | 340.00           (non-medicines need no unit)
Lines starting with # are ignored. Copy the bill's printed total into total.txt (just the number) if you want the sum checked.
