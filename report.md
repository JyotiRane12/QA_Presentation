# QA Project Challenges

## Scope

- **Issues:** SMT-51974

---

## Challenges from JIRA

### SMT-51974: UCE Email template to support all versions on browser and desktop app

- **Status:** Released
- **Description (excerpt):** UCE Email template to support all versions on mobile and windows system...

**Comments:**
- *RajeshRaikar:* [~accountid:5c8208833fb39d723db26978]  As discussed , please verify below issue in STG ,
Add the proof if its working then move ticket for ready for QA
[https://netcoresolutions.atlassian.net/browse/SMT-54441|https://netcoresolutions.atlassian.net/browse/SMT-54441|smart-link] 
[https://netcoresoluti
- *Nikunj V. Pandit:* STG1 proof with {{uce_optimise_html_enabled}} disabled and MJML enabled
[https://app.emailonacid.com/app/acidtest/mccAFE4LiKVNqRfN6DEO13cpfBP9xRWKjnmpU0asbZb2n/list|https://app.emailonacid.com/app/acidtest/mccAFE4LiKVNqRfN6DEO13cpfBP9xRWKjnmpU0asbZb2n/list]
- *Ujjwal Rajpal:* code review done with @Nikunj V. Pandit for MJML flag.
- *Nikunj V. Pandit:* {{uce_mjml_enabled}}flag is added to enable/disable MJML conversion.
- *Jyoti Rane:* QRB Done.
- *RajeshRaikar:* !image-20260105-101553.png|width=715,alt="image-20260105-101553.png"!
- *Prashanth:* Pls go ahead
- *RajeshRaikar:* IND idc evidence with flyflair template
[https://app.emailonacid.com/app/acidtest/P39RD64fvkZybrtbNe9qD995JkAgLPKgA4ncdVguLav6w/list|https://app.emailonacid.com/app/acidtest/P39RD64fvkZybrtbNe9qD995JkAgLPKgA4ncdVguLav6w/list]

MJML_enable_ODO_disable_with_picker
[https://app.emailonacid.com/app/acid
- *RajeshRaikar:* US idc evidence with flyflair template
[https://app.emailonacid.com/app/acidtest/PTMeYxLFb6of9k7WBVayYGSZFQ4ZsOQrhc0la90OShoRc/list|https://app.emailonacid.com/app/acidtest/PTMeYxLFb6of9k7WBVayYGSZFQ4ZsOQrhc0la90OShoRc/list]
MJML_with basic_elements
[https://app.emailonacid.com/app/acidtest/dYhvLvjc
- *Deepesh:* as per [~accountid:61b9bbdb57d5c3007119f38f] the GA will be done around Feb months

asked SRE to enabled for [https://netcore.freshdesk.com/a/tickets/4922591|https://netcore.freshdesk.com/a/tickets/4922591|smart-link] given customer as well - ringgitplus_cee

**Linked issues:**
- Relates: **SMT-51647** — flyflaircee || Outlook compatibility issue in UCE Email (Released)
- Blocks: **PEDS-10817** — Email formatting error for outlook email : Ticketpro (Closed - Waiting for Permanent Resolution)
- Relates: **SMT-54441** — Unable to save email template and getting error in save_template API (Released)
- Relates: **SMT-54448** — Button is not properly shown in email   (On Hold)
- Relates: **SMT-54449** — Email not shown properly in desktop outlook  (Released)
- Relates: **SMT-54450** — Product feed data is broken in test mail (Released)
- Relates: **SMT-54557** — Table Layout Rendering Issue (Released)
- Relates: **SMT-54559** — Table is missing issue (Released)
- Relates: **SMT-54560** — Image not rendering  issue (On Hold)
- Relates: **SMT-54561** — Inside a two-column layout image is not rendering issue (Released)
- Relates: **SMT-54562** — Two-column layout is not rendering properly (Released)
- Relates: **SMT-54580** — Block border and Element border are not shown in the Preview  (On Hold)
- Relates: **SMT-54582** — The Background Image(For element) is not visible in the preview (On Hold)
- Relates: **SMT-54584** — Paragraph Text Missing in Display (Released)
- Relates: **SMT-54586** — Hidden Element Still Visible on Desktop View (Released)
- Relates: **SMT-54587** — Image Overlapping Inside 4-Column Layout (Released)
- Relates: **SMT-54588** — All Layout(2,3,4) Types Display Horizontally Instead of Column View (Released)
- Relates: **SMT-54589** — Individual Elements Not Rendering in Test Emailonacid mail (Released)
- Relates: **SMT-54591** — Customized Social Icon (GIF) Breaks Inside 4-Column Layout (On Hold)
- Relates: **SMT-54596** — when we add product feed with 3 image and 3 products with list view then product feed block not shown in editor (Released)
- Relates: **SMT-54597** — Product feed block background color not getting applied in live preview (On Hold)
- Relates: **SMT-54598** — Product feed block not shown properly ,product feed layout color getting overlap in few desktop browsers (Development Review)
- Relates: **SMT-54599** — Product feed with Two column and 3 column layout not shown properly  in few devices (Released)
- Relates: **SMT-54600** — Product feed button is not shown properly with 3 column layout  in few devices (Released)
- Relates: **SMT-54625** — Italic Formatting Not Applied to Button Text in Product fed static template (Released)
- Relates: **SMT-54628** — Image Overlap and Layout Break in Mobile Preview for Left/Right Image Alignment (Released)
- Relates: **SMT-54645** — Coupon Block Background Color Not Displayed (Released)
- Relates: **SMT-54654** — Image not shown in product collection template  in outlook (Released)
- Relates: **SMT-54702** — AMP fallback mail not rendering properly in outlook (Released)
- Relates: **SMT-54708** — In the Product Picker Button, the alignment is not working  (On Hold)
- Relates: **SMT-54772** — [Flyfair-UCE] 3-Column Layout Rendering Issue in Preview (On Hold)
- Relates: **SMT-54773** — [Flyfair-UCE] Padding Issue in Ediator and Mobile Preview (Released)
- Relates: **SMT-54774** — [Flyfair-UCE] Footer “Contact Us” Spacing Mismatch (Released)
- Relates: **SMT-54776** — [Flyfair-UCE] Image Width Issue in 2-Column Layout (Editor & Preview) (Released)
- Relates: **SMT-54834** — Default Email Body Border Not Visible in preview (Released)
- Relates: **SMT-54877** — Layout Breaks After Applying Background Image (On Hold)
- Relates: **SMT-54887** — [Flyfair-UCE] 3-Column Layout Showing Duplicate Row in Desktop Outlook versions (On Hold)
- Relates: **SMT-54889** — [Flyfair-UCE] 2-Column Layout and Image are missing (Released)
- Relates: **SMT-55002** — Table Centre Alignment Issue (Open)
- Relates: **SMT-55009** — Yahoo Mail Content Overflow & Image Overlap Issue (On Hold)
- Relates: **SMT-55010** — Table Background Image Not Applying (On Hold)
- Relates: **SMT-55011** — Product Picker Frame Left Alignment Issue (Open)
- Relates: **SMT-55012** — Product Picker Content Breakage Issue (Open)
- Relates: **SMT-55013** — Product Picker Image Overlapping in Mobile View (Open)
- Relates: **SMT-55040** — Flyflair template getting clipped in gmail (Released)
- Relates: **SMT-55057** — when we apply AB ,BA and A/B  property , mobile view and desktop view not working  properly (Open)
- Relates: **SMT-55058** — In flyflair email template   icon image alignment not proper in outlook (On Hold)
- Relates: **SMT-55095** — [ODO] : footer mail link not shown properly in mobile and outlook devices (Released)
- Relates: **SMT-55109** — [ODO]: Custom HTML Content Missing in Header Section (Released)
- Relates: **SMT-55110** — [ODO]: Product Feed 3-Column Alignment Breaks (Released)
- Relates: **SMT-55112** — [ODO]: “+274 More” Block Alignment Issue (Released)
- Relates: **SMT-55113** — [ODO]: Footer Content Layout Breaks (Released)
- Relates: **SMT-55114** — [ODO]: 2-Column Layout Breaks Above Footer Section (Released)
- Relates: **SMT-55116** — [ODO]: Content Block Padding Issue (Released)
- Relates: **SMT-55117** — [ODO]: Template Content Missing (Released)
- Relates: **SMT-55124** — [ODO]: Header Timer Not Visible (Released)
- Relates: **SMT-55174** — [ODO]: 2-Column Layout of Header Breaks in Mobile Preview – Timer and Content Show Row-wise (Released)
- Relates: **SMT-55228** — Two column layout not shown properly in  AMP fallback mobile  view (On Hold)
- Relates: **SMT-55236** — [No flag] Column Border Color Not Displayed in Preview (On Hold)
- Relates: **SMT-55261** — ODO template getting clipped when we receive email via journey (On Hold)
- Relates: **SMT-55263** — [No flags] Two-Column Layout Renders as Mobile View in Yahoo Mail on Desktop (On Hold)
- Relates: **SMT-55291** — [Flyflair] 3-Column Layout Break in Outlook App iPhone 13 (On Hold)
- Relates: **SMT-55334** — BA mobile layout styles are applied in Desktop Preview when custom width is set to 100% (On Hold)
- Relates: **SMT-55335** — Mobile Editor shows A|B column layout instead of default AB when Desktop custom width is applied (On Hold)
- Relates: **SMT-55357** — [ODO - enable] Two-Column Layout Renders as Mobile View in Mobile Editor and Preview Despite Desktop Layout Enabled (Open)
- Relates: **SMT-55365** — Email content not shown properly when clipped (Open)
- Relates: **SMT-55378** — In AMP fallback , column background color not getting applied (Open)
- Relates: **SMT-55379** — [No flag] Mobile Editor shows A|B layout instead of default AB for two-column layout when Desktop column width is applied and Button element is present (Open)
- Relates: **SMT-55385** — [No flag] 3-column and 4-column layouts render as columns in mobile view in Acid preview instead of stacking one by one (Open)
- Relates: **SMT-54833** — [UCE] Coupon Background Image Removed When Editing (Gradient Style) (Open)
- Relates: **SMT-54864** — [UCE] Personalization UI Breaks After Adding Product Feed in the Editor (Open)
- Relates: **SMT-55260** — [UCE] Column Background Image Removed When Column Padding Is Cleared in Desktop Preview. (Open)
- Relates: **SMT-54577** — [UCE] Layout borders are not visible in Preview (Open)
- Relates: **SMT-55393** — Dynamic block not shown in editor preview when we enable MJML flag (Open)
- Relates: **SMT-55417** — [Dynamic block] Dynamic Condition Signature Not Displayed in Live Preview (Open)
- Relates: **SMT-55427** — [Dynamic block] Product Feed Not Rendering in Desktop Version on Email on Acid (Open)
- Relates: **SMT-55430** — [Dynamic block] Personalization Not Appended Correctly – Shows [% Integer %] in Test Email (Open)
- Relates: **SMT-55449** — [Product feed] Product Feed Not Rendering in Email on Acid Preview (With or Without MJML) (Open)
- Relates: **SMT-55552** — [Dynamic block] Dynamic Block Not Hidden When Personalization Attribute Value Is Null (Open)
- Relates: **SMT-55563** — table column text alignment is not getting applied properly when MJML is enabled (Open)
- Relates: **SMT-55650** — when we enable MJML flag , social media element allignment not working properly (Open)
- Relates: **SMT-55681** — [ODO] Template content missing in Microsoft 365 (Edge, Windows 10) (Open)
- Relates: **SMT-55973** — [MJML enable]Column layout breaks when personalization is added (Open)


---

## Linked issues summary

- **Total linked issues (unique):** 83

### By issue type

- **Bug:** 68
- **PEDS Internal:** 15

### By priority

- **P0:** 46
- **P1:** 37

---

## Challenges from Slack (project channel)

- **1771328537** | USLACKBOT: <@U0AFJCBQEDS> joined #qa-challenges. They’re also new to Netcore Cloud Private Limited.
- **1771327771** | U0484KCV7UH: <@U04PX3PTXU7>:
Editor is breaking in preprod after deploying merge branch  protected-CEPI-797+SMT-52355
why stg1 url is called in preprod :alert_slow:
*This is blocking preprod testing of CloudFront*
- **1771327749** | U0484KCV7UH: QA update : *04-12-2025*
1. SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Total  issue : 25
Ready for QA : 1
Open issues : 4
Dev Ip: 8
Blocker issue : 0
Test cove
- **1771327720** | U0484KCV7UH: *Hi <@U047QCRAZAT>* *<@U0490SPM8E4>* 
I want to highlight a critical dependency risk impacting multiple high-priority items.
Yesterday, Nikunj shared updates on several open P0/P1 issues (<https://net
- **1771327686** | U0484KCV7UH: <@U04887CNEH3> <@U04A6DFG4BS> Still issues not fixed, please check on priority:alert_slow:
<https://netcoresolutions.atlassian.net/browse/SMT-54586>
<https://netcoresolutions.atlassian.net/browse/SMT-
- **1771327620** | U0484KCV7UH: QA update : *02-12-2025*
1. SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Total  issue : 25
Ready for QA : 1
Open issues : 5
Dev Ip: 7
Blocker issue : 0
Test cove
- **1771327590** | U0484KCV7UH: <@U096VFD0AJW>, <@U048ACSQXPD>, :alert_slow:
<@U084KL1EWG6> is following up on this since yesterday at least we can expect the acknowledgement.
Kindly let us know the challenge so that we can plan and
- **1771327556** | U0484KCV7UH: <@U04A6DFG4BS> Button is not properly shown in email --- &gt; Still issue not fixed for the following devices:
Here, the drag and drop without modification button shows as a dot, but the modified butt
- **1771327524** | U0484KCV7UH: <@U047YU0J4NP> : Below issues <@U04887CNEH3> need to check
<https://netcoresolutions.atlassian.net/browse/SMT-54654>
<https://netcoresolutions.atlassian.net/browse/SMT-54645>
<https://netcoresolutions
- **1771327501** | U0484KCV7UH: QA update : 01*-12-2025*
1. SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Total  issue : 24
Ready for QA : 7
Open issues : 4
Dev Ip: 4
Blocker issue : 0
Test cove
- **1771327469** | U0484KCV7UH: <@U051JV1J02D> <@U0490AQ5QFJ> *coupon is working for test  mail , unable to send via broadcast , please chec*k
- **1771327386** | U0484KCV7UH: DEV update : *29-11-2025*
SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Total  issue : 21
Ready for QA : 8
Open issues : 4
On hold : 9 (Email not rendering proper
- **1771327359** | U0484KCV7UH: QA update : *29-11-2025*
1. SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Total  issue : 21
Ready for QA : 3
Open issues : 18
Blocker issue : 0
Test coverage: 60%
- **1771327320** | U0484KCV7UH: <@U047J3QUCR4> Please ignore
- **1771327310** | U0484KCV7UH: *QA update :* 28-11-2025
1. SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Open issue : 16
Ready for QA : 0
Blocker issue : 0

Test coverage: 50%
Pending:
Coupon b
- **1771327285** | U0484KCV7UH: *QA update :* 27-11-2025
1. SMT-51974 --- UCE Email template to support all versions on browser and desktop app
Open issue : 8
Ready for QA : 0
Blocker issue : 0

---

## Summary for presentation

- Total issues reviewed: 1
- Total linked issues (unique): 83
- Slack messages included: 16

Use the sections above as talking points: JIRA comments and linked issues often surface blockers, env issues, and scope changes.
