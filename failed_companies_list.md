# Failed Companies List

This document summarizes the companies that we have identified as problematic for document extraction from the Mintos platform.

## Confirmed Failing Companies

The following companies consistently fail document extraction with 404 errors:

1. **Iuvo**
   - Error: All URL patterns returned 404 errors
   - URLs attempted:
     - https://www.mintos.com/en/loan-originators/iuvo/
     - https://www.mintos.com/en/lending-companies/iuvo/
     - https://www.mintos.com/en/loan-originators/iuvo
     - https://www.mintos.com/en/lending-companies/iuvo

2. **Iuvo Group**
   - Error: All URL patterns returned 404 errors
   - URLs attempted:
     - https://www.mintos.com/en/loan-originators/iuvo-group/
     - https://www.mintos.com/en/lending-companies/iuvo-group/
     - https://www.mintos.com/en/loan-originators/iuvo-group
     - https://www.mintos.com/en/lending-companies/iuvo-group
     - https://www.mintos.com/en/loan-originators/iuvogroup/
     - https://www.mintos.com/en/lending-companies/iuvogroup/

3. **Eleving Group**
   - Error: All URL patterns returned 404 errors
   - URLs attempted:
     - https://www.mintos.com/en/loan-originators/eleving-group/
     - https://www.mintos.com/en/lending-companies/eleving-group/

## Successful Companies

The following companies were successfully tested for document extraction:

1. **Wowwo**
   - Success URL: https://www.mintos.com/en/loan-originators/wowwo/
   - Documents found: 3
   - Document types: Presentation, Financials, Loan Agreement

2. **Creditstar**
   - Success URL: https://www.mintos.com/en/loan-originators/creditstar/
   - Documents found: 2
   - Document types: Presentation, Financials

3. **Mogo**
   - Success URL: https://www.mintos.com/en/loan-originators/mogo/
   - Documents found: 1
   - Document type: Financials

## Possible Reasons for Failures

1. **Company no longer on platform**: The company may have been removed from the Mintos platform.
2. **URL structure change**: Mintos may have updated their URL structure for certain companies.
3. **Company renamed or rebranded**: The company may be operating under a different name now.
4. **Specialized content loading**: Some companies may require specialized JavaScript rendering or have different content loading patterns.

## Recommended Solutions

1. **Implement robust fallback mechanisms**:
   - Try additional URL patterns
   - Implement fuzzy matching for company names/IDs
   - Use the main Mintos search functionality to locate companies

2. **Regular company URL validation**:
   - Periodically validate all company URLs
   - Update mapping when changes are detected

3. **Error reporting**:
   - Log detailed information when document extraction fails
   - Alert when previously successful extractions start failing