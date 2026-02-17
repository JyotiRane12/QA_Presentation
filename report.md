# QA Project Challenges

## Scope

- **Issues:** CEPI-5451

---

## Challenges from JIRA

### CEPI-5451: Unified Reporting & Section Consolidation for Content Personalization (CPZ)

- **Status:** Deployment Completed
- **Description (excerpt):** h2. *1. Overview*

This project introduces:

h3. *A. Unification*

A new *“Personalized Content”* section that merges *Web PZ + App PZ* into a single unified view.

h3. *B. Detailed Reporting*

A brand-new *Detailed Report module* for Web PZ, aligned with capabilities already available in offsite channels like email campaigns

h3. *C. Data Platform Migration*

Migration of Web PZ reporting from *MongoDB → Vertica*, establishing a unified analytics backend.

h3. *D. Transitional Behavior (30-day...

**Comments:**
- *nitin.patil:* [~accountid:5fdae4d1d36496013901b6d0] pls chk tkt has been released on US idc.
- *Aravinda V:* [~accountid:557058:1ca0f336-7299-49bb-a5bf-1b589d94022e] We are getting audience id in detailed reprort issue on production we need to do hot fix, can you please go give approval for release .
- *Prashanth:* Pls go ahead
- *nitin.patil:* [~accountid:557058:25134401-4f16-4dc4-940b-c43f77094035] [~accountid:5fdae4d1d36496013901b6d0] pls chk smartech-app has been released on US and IND idc.
- *Aravinda V:* Points got on review and fixed : 

h3. _1. Submitted (Total Responses) Column_

* _Current Behavior_: It will be 0 only for inline if no submitted data is present; otherwise, it is NA for the summary.--Issue fixed 

h3. _2. Conversion Column Behavior_

* _Current_: Displays Total Conversions for CPZ
- *Aravinda V:* ON IND idc : 

!image-20260108-060404.png|width=720,alt="image-20260108-060404.png"!

!image-20260108-060357.png|width=720,alt="image-20260108-060357.png"!

!image-20260108-060350.png|width=720,alt="image-20260108-060350.png"!

ON US idc: 

!image-20260108-060458.png|width=811,alt="image-20260108-06
- *Anujkumar Pandey:* Hi [~accountid:615ea6ab9cdb930072952da0] 
Please release smartech-migration branch (CEPI-6642) on Ind and US IDC.

RCA: Yesterday, There was release of [https://netcoresolutions.atlassian.net/browse/CEPI-5451|https://netcoresolutions.atlassian.net/browse/CEPI-5451|smart-link]. which has deployed som
- *nitin.patil:* [~accountid:557058:25134401-4f16-4dc4-940b-c43f77094035] [~accountid:609bb8b15d67f20069ca40e0] pls chk 2 to 5 steps has been released on EU idc.
- *ajay yad:* [~accountid:612f68e7b1894f007173224f] [~accountid:5fdae4d1d36496013901b6d0] your tkt has been released on all IDC
- *Aravinda V:* On EU idc: 

!image-20260114-115119.png|width=831,alt="image-20260114-115119.png"!

!image-20260114-115135.png|width=811,alt="image-20260114-115135.png"!

!image-20260114-115238.png|width=811,alt="image-20260114-115238.png"!

[^41910-Campaign_Multi_Web_cpz_Summary_20260114-c6c52b4d-784a-4d0b-87ff-e9

**Linked issues:**
- Polaris datapoint work item link: **CEPI-5433** — CPZ: Inline Widgets Milestone 2 (Deployment Completed)
- Relates: **SMT-54242** — Form submission error  (Released)
- Relates: **SMT-54249** — Getting 502 bad gateway , api calls are failed for Personalised content on pod2 (Released)
- Relates: **SMT-54253** — Operator column is missing from direct download of summary report (Released)
- Relates: **SMT-54257** — For Detailed report in campaign details, website ddm option is missing in Export report  (Released)
- Relates: **SMT-54334** — Event is passed from Js but in Vertica DB data not inserted (Released)
- Blocks: **LED-25** — Reports not Received in email for the detailed report on WEBCPZ . (Closed)
- Relates: **LED-28** — Getting 502 Bad gateway for user exists api call (Closed)
- Relates: **SMT-54398** — [CPZ report]:Campaign names shows outside the box under campaign download popup window  (Released)
- Relates: **SMT-54399** — [CPZ report]: Total response count not getting on summary reports but count is shown in campaign listing dashboard   (Released)
- Relates: **SMT-54402** — [CPZ report]: Performance/ Report view api calls are taking too much time to load the the count  (Released)
- Relates: **SMT-54421** — [CPZ report] : The counts not loading on webpersonalization listing page  (Released)
- Relates: **SMT-54428** — [CPZ report] Getting null data in get personalization api call on pod2 (Released)
- Relates: **SMT-54431** — [CPZ report] : Not getting conversion and revenue count for content personalization on pod2 (Released)
- Relates: **LED-36** — Not getting OTP for download report in download log for web_cpz (Closed)
- Relates: **SMT-54472** — [CPZ report] : The conversion and revenue count not shown in view report for control group enabled campaign  (DEVELOPMENT IP)
- Relates: **SMT-54475** — [CPZ report]: IP address is not getting shown in detailed report download for the form submission users (Released)
- Relates: **SMT-54481** — [CPZ report] All the tags shown in campaign creation page are not shown under tag section in down load report  (Ready for QA)
- Relates: **SMT-54497** — for web-cpz Summary report after download getting web-message summary report with empty data (Released)
- Relates: **SMT-54498** — web campaign priority giving error toast  (DEVELOPMENT IP)
- Relates: **SMT-54520** — tags value displayed null in summary report (Released)
- Relates: **SMT-54523** — [CPZ report]: Getting undefined when use click on apply changes for recently viewed widget and inline widget on pod2 (Released)
- Relates: **SMT-54524** — website and tag is empty in downloaded summary report (Released)
- Relates: **LED-39** — [CPZ report]: Getting undefined when use click on apply changes for recently viewed widget and inline widget on pod2 (Closed)
- Relates: **SMT-54532** — [CPZ report] Unable to download the summary reports when user select all campaign check box and click on download summary report (Released)
- Blocks: **SMT-54534** — [CPZ report]: User cant able to donwload the direct summary reports for web pz when user selects all the campaign checkbox and getting toaster error message (Released)
- Relates: **SMT-54541** — [CPZ report] Getting no data found in the campaign name section when user selects all the tags in download report section  (Released)
- Relates: **SMT-54567** — [CPZ report] : conversion count and revenue counts are missmatch between dashboard and vertica db  (Released)
- Relates: **LED-45** — Not able to create amazon S3 bucket on pod2  (Closed)
- Relates: **SMT-54592** — scheduled summary report for months getting empty data (Released)
- Relates: **SMT-54670** — [CPZ report] : Report download for GCS is failed on pod2  (Released)
- Blocks: **LED-62** — Lambda not getting updated (Closed)
- Blocks: **LED-63** — Facing access denied issue (Closed)
- Relates: **LED-69** — [CPZ report]: Getting 502 bad gate way error for the CPZ editor  (Closed)
- Relates: **LED-70** — [CPZ report] : user_exists api call failing on pod2 (Closed)
- Relates: **SMT-54865** — [CPZ report]: Getting error in EL for the encryption website events on pod2  (Released)
- Relates: **SMT-54868** — [APP-CPZ]:Issue with the UI counts are not showing on for Personalized content for APZ campaign (Released)
- Relates: **SMT-54990** — [Personalized content]: Issue with filter icon with dropdown (Released)
- Blocks: **SMT-55108** — Journey-Detailed-Scheduler-Report Jobs went error. (Open)
- Relates: **CEPI-6773** — [CPZ report] : conversion count and revenue counts are not shown in smartech panel and vertica db  (To Do)
- Relates: **LED-154** — Generic event transformer build is taking more than 2 hours  on pod2  (Closed)
- Relates: **LED-156** — Getting conflict issues for smartech angular and smartech app components due to the “Squash commits” option is not selected (In Progress)
- Relates: **SMT-55529** — Generic events are failed in EL for CPZ  (Open)
- Relates: **SMT-55916** — Getting NA in detailed report for the Browser, device, page url columns for CPZ report  for view and click activities. (Released)
- Relates: **LED-186** — CPZ events not processed on EU idc due to message router setup is not done (Closed)


---

## Linked issues summary

- **Total linked issues (unique):** 45

### By issue type

- **Bug:** 42
- **Story:** 2
- **PEDS Internal:** 1

### By priority

- **P0:** 14
- **P1:** 31

---

## Summary for presentation

- Total issues reviewed: 1
- Total linked issues (unique): 45

Use the sections above as talking points: JIRA comments and linked issues often surface blockers, env issues, and scope changes.
