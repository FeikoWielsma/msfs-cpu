# Affiliate launch notes

## Before applying

- Publish `/about/` and its links from all three tool pages.
- Check that `msfs@razortek.nl` receives mail. This is the public project contact.
- Finish the separate price refresh; keep real capture dates and estimate markers.
- Publish `/privacy/`. It describes GitHub Pages hosting, privately self-hosted Umami
  in the Netherlands, Mailgun forwarding to Gmail, and Ko-fi supporter data.
- Set an intentional analytics retention period and implement it on the server before
  promising automatic expiry. Inspection on 2026-10-17 found no expiry setting in the
  checked Umami environment/application keys or cleanup schedule in the checked config.
  Proxy access logs rotate at up to 14 days; backups are configured for 28 days with
  a Google Drive copy; service-output logs rotate by size. The policy discloses this
  current state rather than promising deletion that has not been implemented.
- Review provider agreements and international-transfer safeguards for the services
  actually used. A privacy notice describes practices; it is not a compliance certification.
- Apply using `https://msfs.razortek.nl/` as the owned website. Describe the original
  analysis, normalization, build generator and editorial judgement, and acknowledge
  the third-party benchmark sources. The official Discord is a referral source,
  not a property owned by this project or an endorsement.

## Application routes

- Amazon: https://partnernet.amazon.nl/
- ALTERNATE NL: https://www.alternate.nl/Affiliate (TradeTracker)
- Megekko NL: https://tradetracker.com/nl/campaigns/elektronica-en-witgoed-10/megekko-nl-34211/
- Azerty NL: https://adtraction.com/nl/adverteerder/1439952198
- bol: https://affiliate.bol.com/nl/
- Coolblue: https://www.coolblue.nl/c/affiliate-aanmelden-voorwaarden.html (Awin)

Check live campaign terms, approval requirements, eligible products, countries and
commission rates in each account. Joining a network does not guarantee retailer approval.
Amazon's Dutch application guidance asks for recent, substantial original content;
it gives ten posts as a rule of thumb and reviews after three qualifying sales in
180 days. A tool-led site is not guaranteed acceptance. Personal orders do not count.
Reference: https://partnernet.amazon.nl/help/node/topic/G8TW5AE9XL2VX9VM

## When adding retailer links

- Use issued account IDs and exact product destinations; never publish dummy tags.
- Start with a few relevant CPU/GPU links on `/specs/`, matched to the selected country.
- Keep retailer destinations in a separate mapping, outside scores and recommendation logic.
- Label shopping links as affiliate links near the links themselves, with an explanation
  that qualifying purchases may earn commission. Use `rel="sponsored noopener noreferrer"`
  when opening them in a new tab.
- Update `/about/#funding`: remove the statement that no affiliate links are active.
- Add Amazon's required Associate statement when participation starts. Do not describe
  shopping through Amazon links as a way to support the project; keep Ko-fi support separate.
- Use independently sourced descriptions and imagery for listings with multiple retailers.
  Amazon-provided content must not promote competing retailers.
- Do not label reference prices as Amazon offers. Review current Amazon pricing/API rules
  before displaying Amazon prices, availability, or images.
- Review privacy disclosures and tracking before adding any affiliate script or pixel.
  Initial text links do not require an embedded shopping widget.
- Use network reporting for the first trial. Review clicks, confirmed sales and net
  commission after 6–8 weeks rather than adding extra tracking immediately.
- Review hosting terms if the site's primary purpose becomes commercial; it currently
  uses GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

This preparation does not claim any retailer affiliation or guarantee approval.
