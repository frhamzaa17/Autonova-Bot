# Platform API Research Report - Phase 1

Research target: 99acres, MagicBricks, Housing.com, and NoBroker for Phase 2 listing and lead integrations.

## Summary

Most Indian real-estate portals do not provide open public listing APIs for general developers. Production integration usually requires partner, broker, builder, or enterprise access. For Phase 2, the recommended path is to first use official partner channels where available, avoid scraping unless written permission exists, and design an internal listing export workflow as a fallback.

## Platform Findings

| Platform | Public API Status | Likely Supported Actions | Limits / Cost | Phase 2 Recommendation |
| --- | --- | --- | --- | --- |
| 99acres | No broadly documented public API for general listing automation. Partner/business access may exist through sales channels. | Listing creation, inventory sync, lead retrieval may be possible only through private/partner arrangements. | Not publicly listed; likely commercial contract. | Contact 99acres business/partner team. Build CSV/export adapter meanwhile. |
| MagicBricks | No general public API documented for posting listings. Business products and broker/builder tools exist. | Lead management and listing promotion may be available through paid business products. | Commercial, plan-dependent. | Use official business account workflows first; request API/CRM integration details. |
| Housing.com | No open public API found for generic posting. Developer access appears private or partner-led. | Listing syndication and lead delivery may be available to channel partners. | Commercial or partner-only. | Explore partner onboarding; do not scrape without approval. |
| NoBroker | No public listing API for arbitrary automated posting. Services are consumer/business-product driven. | Lead/listing flows likely controlled through app/web account interfaces. | Not publicly listed. | Treat as manual or semi-automated Phase 2 integration unless NoBroker grants partner access. |

## Integration Strategy

1. Create a normalized internal listing schema:
   - property ID, title, type, transaction type, address, locality, city, price/rent, area, bedrooms, furnishing, amenities, owner/contact, photos, description, availability.
2. Build export adapters:
   - CSV export for portal bulk upload.
   - human-review checklist before publishing.
   - per-platform field mapping.
3. Use official partner APIs only after written approval and credentials.
4. Keep a lead-ingestion interface ready:
   - email parser, CSV upload, webhook endpoint, or CRM import.
5. Log every outbound listing action for auditability.

## Risks

- Terms-of-service violations if scraping or browser automation is used without permission.
- Duplicate listings or stale prices if synchronization rules are weak.
- Client data exposure if portal credentials are mishandled.

## Phase 2 Recommendation

Start with CSV/export plus manual review in week 1 of Phase 2. In parallel, contact platform sales/partner teams for API access. Add direct API integrations only for portals that provide official access, clear terms, and stable credentials.

