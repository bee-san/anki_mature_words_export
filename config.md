`deckName`
The deck searched with `deck:"<name>"`.

`matureDays`
Cards with `prop:ivl>=matureDays` count as mature. Default: `21`.

`fieldName`
Field read from each included note. HTML is stripped and the text is split on line breaks. Default: `Expression`.

`httpPort`
Port used by the local update server for Yomitan updates. Default: `8766`.

`includeSuspended`
If `false`, `-is:suspended` is added to the search query. Default: `false`.

`dedupeStrategy`
Currently only `case_sensitive_trim` is supported. Terms are trimmed, deduplicated exactly, then sorted. Default: `case_sensitive_trim`.

`noteCardRule`
`any_mature_card` includes a note when at least one card in scope is mature. `all_cards_mature` includes a note only when every in-scope card is mature. Default: `any_mature_card`.
