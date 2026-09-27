# Mock scenarios

These handlers model special UI conditions without changing the default mock
API contract. Import the required handler and place it before the default
handlers for a focused test or manual development session.

- `slowUpload.ts`: adds a 1.5-second upload response for progress-state testing.
