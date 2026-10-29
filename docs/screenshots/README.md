# Application screenshot provenance

These four PNGs are genuine viewport captures of the local Streamlit application,
made on 2026-10-28 with headless Edge 156.0.4314.50. They use only the fictional
`sample_data/portfolio_sales_raw.csv` dataset and the seven-step portfolio workflow.
No pixels, metrics or table values were edited or generated. Captures were inspected
after rendering; no source/backend code was changed for the screenshots.

| Capture | State |
| --- | --- |
| [01-dashboard-overview.png](01-dashboard-overview.png) | Original synthetic data, before processing. |
| [02-cleaning-configuration.png](02-cleaning-configuration.png) | Seven ordered steps, explicit date formats visible. |
| [03-before-after-results.png](03-before-after-results.png) | Reviewed preview, original and result side by side, before confirmation. |
| [04-downloads.png](04-downloads.png) | Confirmed result, prepared downloads and real precision warning. |

Each image is 1440 × 1050 pixels. Viewport/table scrolling means not every row or
column is visible at once; exports contain all confirmed data. The built-in Streamlit
“Deploy” control is visible in the application chrome; it does not mean the app has
been deployed or published.

[capture_manifest.json](capture_manifest.json) records browser version, input SHA-256,
viewport, image sizes and hashes. [Manual capture steps](../portfolio/screenshots.md)
and the [demo workflow](../portfolio/demo_workflow.md) reproduce these states.
Native save dialogs, mobile/accessibility checks and Excel/LibreOffice rendering
remain unverified. There is no fabricated UI mockup or completed demonstration video.
