# AutoNova AI User Manual

AutoNova AI is a Telegram-based business assistant that can answer questions, read uploaded documents, search local business knowledge, create or edit files, transcribe voice notes, generate images, and use Tavily web search when a question needs external or current information.

This manual explains how to talk to the bot so it understands your intent correctly.

## 1. Basic Idea

The bot works best when your prompt clearly tells it:

1. What you want.
2. Whether the answer should come from your uploaded/local documents or from the web.
3. Which file, person, record, table, or topic you are referring to.
4. Whether you want an answer, a list, a count, a calculation, a new document, or an edited file.

Good prompt structure:

```text
Action + target + source/context + output format
```

Examples:

```text
Count agreements expiring within 60 days from the uploaded rental agreement PDF.
List all tenants and their monthly rent from the uploaded document.
Search the web for current home loan interest rates in India and summarize with sources.
Draft a rent reminder letter for Amit Sharma using the rental agreement details.
Update the last document and add a termination clause.
```

## 2. Local Knowledge vs Web Search

AutoNova can answer from two broad sources:

- Local knowledge: uploaded files, structured document data, business records, chat context, generated/edited files.
- Web search: Tavily search or URL extraction for current/general/external information.

Use local wording when you want answers from your files:

```text
from the uploaded PDF
from this document
from my knowledge base
in the rental agreement file
using local records
from the spreadsheet
```

Use web wording when you want external information:

```text
search the web
look up online
latest
current
today
recent news
scrape this URL
```

Examples:

```text
What is Amit Sharma's monthly rent?
```

This is local because `Amit Sharma` is a local tenant record.

```text
What is a rental agreement?
```

This is general knowledge and should use web/general answering.

```text
What does this rental agreement say about expiry?
```

This is local because it refers to `this rental agreement`.

```text
Search web for latest stamp duty rates in Maharashtra.
```

This is web because it asks for latest external information.

## 3. Setting Your Workspace

Use `/company` to separate each business or client workspace.

```text
/company Prestige Realty
```

The bot will store uploaded files, structured knowledge, and chat context under that workspace. Use a different company name for another client or project.

## 4. Uploading Documents

You can upload:

- PDF
- DOCX
- XLSX
- TXT
- MD
- Images, when OCR is available

To save a document for future questions, upload it with a caption like:

```text
save this to knowledge base
remember this document
these are my business details, save them
ingest this
```

Captionless uploads are usually treated as knowledge documents by default.

After upload, ask:

```text
Summarize this document.
What are the key points in the uploaded file?
How many rows are in this spreadsheet?
List the important dates from this PDF.
Find all amounts mentioned in this document.
```

## 5. Asking Questions From Documents

For accurate document answers, mention the file/source clearly.

Good:

```text
How many agreements are expiring soon in the uploaded rental agreement PDF?
List all agreements with tenant name, property ID, rent, start date, end date, and status.
Which agreements expire within 60 days from the document date?
Show the renewal pipeline records from this PDF.
What is the total monthly rent in the uploaded file?
```

Less clear:

```text
Give details.
What about them?
How many are there?
```

Short follow-ups can work after a related question, but clear prompts are more reliable.

Better follow-up:

```text
Give details of those expiring agreements.
List the records counted above.
Show the tenants from the previous answer.
```

## 6. Counts, Totals, and Calculations

The bot can do deterministic calculations from structured records when possible.

Examples:

```text
How many agreements are there?
How many commercial agreements are active?
How many agreements expire within 60 days?
What is the total monthly rent?
What is the average monthly rent?
Which tenant has the highest monthly rent?
What is the total security deposit for residential agreements?
How many contacts are vendors?
```

For pure arithmetic:

```text
calculate 45000 * 12
calculate 2 crore * 1.5%
calculate (32000 + 18500 + 27000)
```

## 7. Listing and Finding Records

Use list/show/find prompts:

```text
List all tenants.
Show all renewal actions.
Find Amit Sharma.
Show records for property PR-005.
List table rows from the uploaded document.
Show contacts assigned to Raj.
List vendors and phone numbers.
```

If there are many results, the bot may show the first set and tell you more are available.

## 8. Generating Documents

Use words like `draft`, `write`, `prepare`, or `create`.

Examples:

```text
Draft a rent reminder letter for Amit Sharma.
Prepare a sales proposal for buyer Rahul Sharma.
Write a report on active rental agreements.
Create a notice for lease renewal discussion.
Draft a rental agreement for Green Valley Residency.
```

The bot can return generated files such as TXT, DOCX, or PDF depending on the workflow.

## 9. Editing Documents

Use clear edit words and identify the target file.

Examples:

```text
Update the last document and add a termination clause.
Replace buyer name with Rahul Sharma in the last agreement.
Change seller name to Priya Mehta in the uploaded DOCX.
Add paragraph: Payment must be completed within 7 days.
Mark all rows as reviewed in the spreadsheet.
Set B2 = 5000 in the spreadsheet.
Formula E2 = SUM(B2:D2).
```

For PDFs, the bot usually extracts text and generates a new edited PDF. It may not preserve the exact original layout.

## 10. Web Search and Scraping

Web search requires Tavily to be enabled in `.env`.

Use web search for:

- latest/current information
- laws, rates, market updates
- product or service recommendations
- general questions not in your local knowledge base
- URLs you want scraped or summarized

Examples:

```text
Search web for latest stamp duty rates in Maharashtra.
What are current home loan interest rates in India?
How to analyse a stock?
Compare top CRM tools for small real estate businesses.
Scrape https://example.com/page and summarize it.
What is today's Nifty market trend?
```

When you want local data, say so:

```text
Using my uploaded files, summarize the rental agreement data.
From local knowledge, list pending rent records.
```

## 11. Voice Notes

You can send a Telegram voice note. The bot will:

1. Transcribe the audio.
2. Treat the transcription like a normal text prompt.
3. Answer, generate, edit, or search based on the transcribed instruction.

Speak clearly and include the source:

```text
From the uploaded rental agreement PDF, tell me which agreements expire soon.
```

## 12. Image Generation

Ask for images using words like `generate`, `create`, `draw`, or `design`.

Examples:

```text
Generate an image of a modern office reception.
Create a banner for a real estate listing.
Draw a 2BHK floor plan with labels.
Design a poster for an open house event.
```

For image follow-ups:

```text
Add labels to the rooms.
Make it brighter.
Change the background to white.
```

## 13. Knowledge Base Management

Useful prompts:

```text
Show my knowledge base.
How many files are in my knowledge base?
List saved files.
Remove Rental_Agreements.pdf from knowledge base.
Clear my knowledge base.
```

Be careful with remove/clear commands because they delete local knowledge records and files.

## 14. Prompt Templates

### Local Document Question

```text
From [file/source], [count/list/summarize/find/calculate] [target] and include [fields].
```

Example:

```text
From the uploaded rental agreement PDF, list agreements expiring soon and include tenant, property, end date, rent, and status.
```

### Web Question

```text
Search the web for [topic] and summarize with sources.
```

Example:

```text
Search the web for current home loan rates in India and summarize with sources.
```

### Document Draft

```text
Draft a [document type] for [person/company/purpose] using [details/source].
```

Example:

```text
Draft a lease renewal notice for Amit Sharma using the uploaded rental agreement details.
```

### Document Edit

```text
Update [file/last document/uploaded document] and [specific change]. Return the updated file.
```

Example:

```text
Update the last agreement and replace buyer name with Rahul Sharma. Return the updated DOCX.
```

### Spreadsheet Edit

```text
In [spreadsheet], [set/formula/update/mark] [cell/column/rows].
```

Example:

```text
In the uploaded spreadsheet, set E2 = SUM(B2:D2).
```

## 15. Tips for Best Results

- Mention `uploaded document`, `this PDF`, or the filename for local questions.
- Mention `search web`, `latest`, or `current` for external questions.
- Ask one task at a time when editing files.
- For calculations, specify the field: monthly rent, deposit, proposed rent, amount due.
- For follow-ups, refer to the previous answer clearly: `those agreements`, `the records counted above`.
- Use IDs and names when possible: `RA-2301`, `PR-005`, `Amit Sharma`.
- For legal/business documents, review generated output before using it officially.

## 16. Common Mistakes

Avoid vague prompts when precision matters:

```text
Give details.
Do it.
Make changes.
What about this?
```

Use clearer prompts:

```text
Give details of the 3 expiring agreements.
Update the uploaded PDF and add a termination clause.
What does this document say about renewal?
List table rows from the uploaded spreadsheet.
```

## 17. Limitations

- PDF editing regenerates files and may not preserve original layout.
- Scanned PDFs and images depend on OCR quality.
- Very complex tables may need manual review.
- Web search only works when Tavily is enabled.
- External services may receive query text or URLs when web/image fallback is enabled.
- The bot is an assistant, not a legal, financial, or compliance authority. Verify important outputs.

## 18. Quick Start

1. Set workspace:

```text
/company Your Company Name
```

2. Upload files with caption:

```text
save this to knowledge base
```

3. Ask local questions:

```text
Summarize uploaded documents.
How many agreements are expiring soon?
List tenants with rent and end date.
```

4. Ask web questions:

```text
Search web for latest market rates.
How to analyse a stock?
What are current home loan rates?
```

5. Generate or edit files:

```text
Draft a rent reminder letter for Amit Sharma.
Update the last document and add a termination clause.
```
