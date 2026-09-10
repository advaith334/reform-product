# Frontend

React, TypeScript and Vite. Three screens' worth of behaviour, deliberately small: upload
a document, browse what you've uploaded, and hover anything to find out how much to trust
it.

## Running it

```bash
npm install
npm run dev
```

Then <http://localhost:5173>. The backend needs to be running on port 8000 — Vite proxies
`/api` to it, so there's no API base URL anywhere in the code and no CORS in development.

```bash
npm run build     # typecheck and bundle into dist/
npm run preview   # serve that bundle
```

## The screens

**The list** is the home page: a dropzone above a table of everything uploaded. Drop a
file and it appears straight away as `Queued`, then `Extracting`, then `Complete`.

**The detail view** puts the extracted fields on the left and the original document on the
right, so you can check one against the other without switching tabs.

## Upload is asynchronous, and the UI has to know that

The backend returns `202` as soon as the file is on disk, because reading a document takes
tens of seconds. Nothing is extracted yet at that point.

So `UploadDropzone` owns the wait. It shows the row immediately, then polls the document
every two seconds until its status leaves `pending`/`processing`. `DocumentDetail` polls
the same way, because opening a document straight after uploading it is the normal thing
to do. If extraction fails, the error comes back on the row and is shown in place — a
failed upload should never look like a hung one.

## Confidence in the interface

Every extracted value in the app — document fields and line-item cells alike — renders
through one component, `ConfidenceValue`. That's deliberate: the colour scale and the
hover behaviour are defined in exactly one place, so they can't drift apart between the
two tables.

Values are tinted by the weakest OCR word behind them: green above 95%, amber above 85%,
red below. Hovering shows the exact numbers and how the value was found on the page.
Column headers and field labels have their own short tooltips explaining what each one
means, which is mostly there to answer the question a blank cell provokes — usually the
field isn't on that document at all, rather than having been misread.

Everything reachable by mouse is reachable by keyboard: the triggers are focusable and the
tooltips are wired up with `aria-describedby`.

### One implementation note worth knowing

Tooltips render into a portal on `document.body` and are positioned with `position: fixed`,
rather than being absolutely-positioned children of what they describe.

This isn't over-engineering. Both tables sit inside an `overflow-x: auto` wrapper so they
can scroll sideways on a narrow screen, and an overflow container clips its descendants on
*both* axes — a tooltip nested inside a row would be sliced off at the row's edge. A
portal escapes the container entirely, and fixed coordinates let the tooltip flip below
its trigger when there's no room above, which is what column headers need.

## Layout

```
src/
  api.ts        One typed function per endpoint
  types.ts      Mirrors the backend's response schemas
  App.tsx       Routes and the list page
  components/
    UploadDropzone.tsx   Drag-and-drop, upload, poll
    DocumentList.tsx     The table of uploads
    DocumentDetail.tsx   Fields beside the original
    LineItemsTable.tsx   The goods table
    ConfidenceValue.tsx  A value plus its confidence — used everywhere
    ColumnHeader.tsx     Header labels and their explanations
    Tooltip.tsx          The portal-positioned tooltip primitive
  styles.css    Plain CSS, no component library
```

`types.ts` is hand-written to match `backend/src/reform/api/schemas.py`. If you change a
response shape on the backend, change it here too — nothing generates one from the other.
