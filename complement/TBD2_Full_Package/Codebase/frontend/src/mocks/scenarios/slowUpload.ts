import { delay, http, HttpResponse } from 'msw'

/**
 * Opt-in slow-upload scenario retained from the original mock handler.
 * Add this handler before the default handlers when testing upload progress UI.
 */
export const slowUploadHandler = http.post('/api/pipelines/:id/upload-input', async () => {
  await delay(1500)
  return HttpResponse.json(
    {
      filename: 'input_metric_values_esgrc.csv',
      r2_key: 'org/1/reference/input_metric_values_esgrc.csv',
      size_bytes: 204800,
      last_modified: new Date().toISOString(),
    },
    { status: 201 },
  )
})
