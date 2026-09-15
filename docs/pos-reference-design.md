# POS reference design

The approved reference is the user's `ChatGPT Image Sep 13, 2026, 01_04_28 AM (2).png`.
Its 1673 × 942 frame includes about 50 pixels of native Electron chrome; the UI viewport is 1673 × 892.

`src/app/pos-reference.css` is the final, POS-scoped stylesheet, loaded after the existing theme. Desktop geometry scales from that reference viewport. The catalogue has four columns with separate live labels, prices, stock indicators, favourite controls and add buttons. The checkout uses explicit row sizes so legacy component styles cannot enlarge payment controls.

The product photography is a newly generated approximation of the supplied artwork, not a pixel-identical extraction. The built-in image-generation tool produced `public/assets/images/products/photos/pos-product-atlas.png`, an equal 4 × 3 atlas. CSS selects its cells without raster cropping or baked-in prices/buttons. The atlas replaces only the known bundled photo paths for the twelve featured products. Other filenames, URLs and tenant uploads continue through the configured asset service. Current prices, availability and favourites remain live catalogue data.

Generation prompt:

> Create a single production sprite-sheet asset from the twelve product card photographs in the reference POS screenshot. Output landscape 1536x864, a seamless equal 4-column by 3-row grid with ZERO gutters/borders between tiles. Each tile exactly 384x288. NO text, names, prices, stock indicators, icons, hearts, plus buttons, card borders, UI, header, navigation, or watermark anywhere. Only product photography. Preserve the reference products closely: row1 orange juice glass with orange half; black coffee in white cup and saucer handle right; clear tall mint/lime mojito; yellow pistachio milk glass. row2 tall whipped chocolate-drizzle milkshake; sesame cheese burger with lettuce/tomato; black bowl of golden fries; chicken burger with sesame bun lettuce tomato. row3 chocolate milkshake; creamy iced cold coffee in tall glass with foam; amber hot tea in beige cup/saucer handle right; two triangular grilled sandwiches on white plate. Every tile: product is located in RIGHT HALF (center x=72% of tile), full product and its base visible, occupying 78-88% tile height; left 42% empty warm ivory #fcf9f2 for live HTML labels. Pale softly blurred cream background, faint natural tabletop/contact shadow, no dark cafe scene. Match reference shape, proportions, appetizing photographic rendering. Uniform independent tiles with no objects crossing the cell boundaries. This is a photo sprite atlas consumed by CSS, exact 4 by 3 geometry is essential.

The tool returned 1672 × 941 instead of the requested pixel dimensions. Percentage-based cell positioning supports that output size.

## Shared header and navigation (1.0.5)

`features/shell/shell.component.css` owns the application header/footer across all authenticated routes. Its component-scoped selectors take precedence over legacy page-specific chrome overrides. Header actions no longer switch order or disappear on POS/dashboard. Footer space is a dedicated grid row, so scrolling page content cannot cover it. The footer is centered, with matching active states and responsive overflow on narrow windows. Role-based navigation permissions remain unchanged; login keeps its separate layout.

Local Electron verification covered all nine administrator navigation screens at widths 1673, 1366, 1024 and 768. Header/footer bounds and action order matched between routes; there was no header overlap, viewport overflow, clipped navigation text, or page/footer overlap. Production build succeeds with the existing initial-bundle size warning.

Visual verification uses the actual local Electron app. Development servers must restart after changing Angular's stylesheet configuration. Version 1.0.4 distinguishes this artwork change from previous 1.0.3 installers.
