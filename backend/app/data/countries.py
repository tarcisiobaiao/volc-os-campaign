"""
Canonical dataset of the 195 sovereign countries (193 UN members + the Holy
See/Vatican + the State of Palestine). SINGLE SOURCE OF TRUTH — the frontend TS
dataset (src/data/pautadorCountries.ts) and the SQL seed
(src/sql/v7_04_seed_all_pautador_countries.sql) are GENERATED from this file
(backend/scripts/gen_country_artifacts.py), so the three never drift.

Territories/dependencies (Taiwan, Hong Kong, Kosovo, Puerto Rico, …) are NOT
included as active sovereign countries here; add them later with is_sovereign=false.

Each country exposes: country_code (ISO2), iso3, country_name (PT-BR), name_en,
name_native, native_language (locale), language_code/short, currency_code,
market_tier, flag_emoji (derived from ISO2), aliases, is_active, is_sovereign,
plus the OPTIONAL Google Ads numbers (null when not confidently known):
  - language_constant      (Google Ads languageConstants)
  - google_ads_geo_target  (Google Ads geoTargetConstants country id)
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional

# --- Google Ads constants — only the values we are confident about ------------
# Anything not listed stays null (the backend falls back honestly, never invents).
LANGUAGE_CONSTANTS: Dict[str, int] = {
    "en": 1000, "de": 1001, "fr": 1002, "es": 1003, "it": 1004, "ja": 1005,
    "da": 1009, "nl": 1010, "fi": 1011, "ko": 1012, "nb": 1013, "no": 1013,
    "pt": 1014, "sv": 1015, "zh": 1017, "ar": 1019, "bg": 1020, "cs": 1021,
    "el": 1022, "hi": 1023, "hu": 1024, "id": 1025, "he": 1027, "lt": 1029,
    "pl": 1030, "ru": 1031, "ro": 1032, "sk": 1033, "sr": 1035, "uk": 1036,
    "tr": 1037, "hr": 1039, "vi": 1040, "th": 1044,
}

# Google Ads geoTargetConstants (country level) — confident subset only.
GEO_TARGETS: Dict[str, int] = {
    "US": 2840, "GB": 2826, "CA": 2124, "AU": 2036, "NZ": 2554, "IE": 2372,
    "DE": 2276, "FR": 2250, "IT": 2380, "ES": 2724, "PT": 2620, "NL": 2528,
    "BE": 2056, "AT": 2040, "CH": 2756, "SE": 2752, "NO": 2578, "DK": 2208,
    "FI": 2246, "PL": 2616, "CZ": 2203, "GR": 2300, "HU": 2348, "RO": 2642,
    "RU": 2643, "UA": 2804, "TR": 2792, "IL": 2376, "AE": 2784, "SA": 2682,
    "EG": 2818, "ZA": 2710, "NG": 2566, "KE": 2404, "JP": 2392, "KR": 2410,
    "SG": 2702, "IN": 2356, "ID": 2360, "PH": 2608, "TH": 2764, "VN": 2704,
    "MY": 2458, "CN": 2156, "BR": 2076, "MX": 2484, "AR": 2032, "CL": 2152,
    "CO": 2170, "PE": 2604, "UY": 2858, "PY": 2600, "BO": 2068, "EC": 2218,
    "VE": 2862, "GT": 2320,
}

# Each row: (iso2, iso3, name_pt, name_en, name_native, native_locale, lang2,
#            currency, market_tier, [extra_aliases])
_RAW = [
    ("AF", "AFG", "Afeganistão", "Afghanistan", "افغانستان", "fa-AF", "fa", "AFN", "volume_play", []),
    ("AL", "ALB", "Albânia", "Albania", "Shqipëria", "sq-AL", "sq", "ALL", "volume_play", []),
    ("DZ", "DZA", "Argélia", "Algeria", "الجزائر", "ar-DZ", "ar", "DZD", "volume_play", []),
    ("AD", "AND", "Andorra", "Andorra", "Andorra", "ca-AD", "ca", "EUR", "medium_value", []),
    ("AO", "AGO", "Angola", "Angola", "Angola", "pt-AO", "pt", "AOA", "volume_play", []),
    ("AG", "ATG", "Antígua e Barbuda", "Antigua and Barbuda", "Antigua and Barbuda", "en-AG", "en", "XCD", "volume_play", ["antigua"]),
    ("AR", "ARG", "Argentina", "Argentina", "Argentina", "es-AR", "es", "ARS", "medium_value", []),
    ("AM", "ARM", "Armênia", "Armenia", "Հայաստան", "hy-AM", "hy", "AMD", "volume_play", []),
    ("AU", "AUS", "Austrália", "Australia", "Australia", "en-AU", "en", "AUD", "high_value", []),
    ("AT", "AUT", "Áustria", "Austria", "Österreich", "de-AT", "de", "EUR", "high_value", []),
    ("AZ", "AZE", "Azerbaijão", "Azerbaijan", "Azərbaycan", "az-AZ", "az", "AZN", "volume_play", []),
    ("BS", "BHS", "Bahamas", "Bahamas", "Bahamas", "en-BS", "en", "BSD", "medium_value", []),
    ("BH", "BHR", "Bahrein", "Bahrain", "البحرين", "ar-BH", "ar", "BHD", "medium_value", ["bahrain"]),
    ("BD", "BGD", "Bangladesh", "Bangladesh", "বাংলাদেশ", "bn-BD", "bn", "BDT", "volume_play", []),
    ("BB", "BRB", "Barbados", "Barbados", "Barbados", "en-BB", "en", "BBD", "volume_play", []),
    ("BY", "BLR", "Belarus", "Belarus", "Беларусь", "be-BY", "be", "BYN", "volume_play", ["bielorrussia"]),
    ("BE", "BEL", "Bélgica", "Belgium", "België", "nl-BE", "nl", "EUR", "high_value", []),
    ("BZ", "BLZ", "Belize", "Belize", "Belize", "en-BZ", "en", "BZD", "volume_play", []),
    ("BJ", "BEN", "Benin", "Benin", "Bénin", "fr-BJ", "fr", "XOF", "volume_play", []),
    ("BT", "BTN", "Butão", "Bhutan", "འབྲུག", "dz-BT", "dz", "BTN", "volume_play", ["butao"]),
    ("BO", "BOL", "Bolívia", "Bolivia", "Bolivia", "es-BO", "es", "BOB", "volume_play", []),
    ("BA", "BIH", "Bósnia e Herzegovina", "Bosnia and Herzegovina", "Bosna i Hercegovina", "bs-BA", "bs", "BAM", "volume_play", ["bosnia"]),
    ("BW", "BWA", "Botsuana", "Botswana", "Botswana", "en-BW", "en", "BWP", "volume_play", ["botswana"]),
    ("BR", "BRA", "Brasil", "Brazil", "Brasil", "pt-BR", "pt", "BRL", "medium_value", ["brazil"]),
    ("BN", "BRN", "Brunei", "Brunei", "Brunei Darussalam", "ms-BN", "ms", "BND", "medium_value", []),
    ("BG", "BGR", "Bulgária", "Bulgaria", "България", "bg-BG", "bg", "BGN", "medium_value", ["bulgaria"]),
    ("BF", "BFA", "Burquina Faso", "Burkina Faso", "Burkina Faso", "fr-BF", "fr", "XOF", "volume_play", ["burkina faso"]),
    ("BI", "BDI", "Burúndi", "Burundi", "Burundi", "fr-BI", "fr", "BIF", "volume_play", ["burundi"]),
    ("CV", "CPV", "Cabo Verde", "Cabo Verde", "Cabo Verde", "pt-CV", "pt", "CVE", "volume_play", ["cape verde"]),
    ("KH", "KHM", "Camboja", "Cambodia", "កម្ពុជា", "km-KH", "km", "KHR", "volume_play", ["cambodia"]),
    ("CM", "CMR", "Camarões", "Cameroon", "Cameroun", "fr-CM", "fr", "XAF", "volume_play", ["cameroon", "camaroes"]),
    ("CA", "CAN", "Canadá", "Canada", "Canada", "en-CA", "en", "CAD", "high_value", []),
    ("CF", "CAF", "República Centro-Africana", "Central African Republic", "République centrafricaine", "fr-CF", "fr", "XAF", "volume_play", ["central african republic"]),
    ("TD", "TCD", "Chade", "Chad", "Tchad", "fr-TD", "fr", "XAF", "volume_play", ["chad"]),
    ("CL", "CHL", "Chile", "Chile", "Chile", "es-CL", "es", "CLP", "medium_value", []),
    ("CN", "CHN", "China", "China", "中国", "zh-CN", "zh", "CNY", "medium_value", []),
    ("CO", "COL", "Colômbia", "Colombia", "Colombia", "es-CO", "es", "COP", "medium_value", ["colombia"]),
    ("KM", "COM", "Comores", "Comoros", "Comores", "fr-KM", "fr", "KMF", "volume_play", ["comoros"]),
    ("CG", "COG", "Congo", "Republic of the Congo", "Congo", "fr-CG", "fr", "XAF", "volume_play", ["republic of the congo", "congo brazzaville"]),
    ("CD", "COD", "República Democrática do Congo", "DR Congo", "RD Congo", "fr-CD", "fr", "CDF", "volume_play", ["dr congo", "democratic republic of the congo", "rdc", "congo kinshasa"]),
    ("CR", "CRI", "Costa Rica", "Costa Rica", "Costa Rica", "es-CR", "es", "CRC", "medium_value", []),
    ("CI", "CIV", "Costa do Marfim", "Ivory Coast", "Côte d'Ivoire", "fr-CI", "fr", "XOF", "volume_play", ["ivory coast", "cote d'ivoire", "cote d ivoire"]),
    ("HR", "HRV", "Croácia", "Croatia", "Hrvatska", "hr-HR", "hr", "EUR", "medium_value", ["croacia"]),
    ("CU", "CUB", "Cuba", "Cuba", "Cuba", "es-CU", "es", "CUP", "volume_play", []),
    ("CY", "CYP", "Chipre", "Cyprus", "Κύπρος", "el-CY", "el", "EUR", "medium_value", ["cyprus"]),
    ("CZ", "CZE", "Tchéquia", "Czechia", "Česko", "cs-CZ", "cs", "CZK", "medium_value", ["czech republic", "republica tcheca", "tchequia"]),
    ("DK", "DNK", "Dinamarca", "Denmark", "Danmark", "da-DK", "da", "DKK", "high_value", []),
    ("DJ", "DJI", "Djibuti", "Djibouti", "Djibouti", "fr-DJ", "fr", "DJF", "volume_play", ["djibouti"]),
    ("DM", "DMA", "Dominica", "Dominica", "Dominica", "en-DM", "en", "XCD", "volume_play", []),
    ("DO", "DOM", "República Dominicana", "Dominican Republic", "República Dominicana", "es-DO", "es", "DOP", "medium_value", ["dominican republic"]),
    ("EC", "ECU", "Equador", "Ecuador", "Ecuador", "es-EC", "es", "USD", "volume_play", ["ecuador"]),
    ("EG", "EGY", "Egito", "Egypt", "مصر", "ar-EG", "ar", "EGP", "medium_value", ["egypt", "egito"]),
    ("SV", "SLV", "El Salvador", "El Salvador", "El Salvador", "es-SV", "es", "USD", "volume_play", []),
    ("GQ", "GNQ", "Guiné Equatorial", "Equatorial Guinea", "Guinea Ecuatorial", "es-GQ", "es", "XAF", "volume_play", ["equatorial guinea"]),
    ("ER", "ERI", "Eritreia", "Eritrea", "Eritrea", "ti-ER", "ti", "ERN", "volume_play", ["eritrea"]),
    ("EE", "EST", "Estônia", "Estonia", "Eesti", "et-EE", "et", "EUR", "medium_value", ["estonia"]),
    ("SZ", "SWZ", "Essuatíni", "Eswatini", "eSwatini", "en-SZ", "en", "SZL", "volume_play", ["eswatini", "swaziland", "suazilandia"]),
    ("ET", "ETH", "Etiópia", "Ethiopia", "ኢትዮጵያ", "am-ET", "am", "ETB", "volume_play", ["ethiopia", "etiopia"]),
    ("FJ", "FJI", "Fiji", "Fiji", "Fiji", "en-FJ", "en", "FJD", "volume_play", []),
    ("FI", "FIN", "Finlândia", "Finland", "Suomi", "fi-FI", "fi", "EUR", "high_value", []),
    ("FR", "FRA", "França", "France", "France", "fr-FR", "fr", "EUR", "high_value", ["france"]),
    ("GA", "GAB", "Gabão", "Gabon", "Gabon", "fr-GA", "fr", "XAF", "volume_play", ["gabon"]),
    ("GM", "GMB", "Gâmbia", "Gambia", "Gambia", "en-GM", "en", "GMD", "volume_play", ["gambia"]),
    ("GE", "GEO", "Geórgia", "Georgia", "საქართველო", "ka-GE", "ka", "GEL", "volume_play", ["georgia"]),
    ("DE", "DEU", "Alemanha", "Germany", "Deutschland", "de-DE", "de", "EUR", "high_value", ["germany"]),
    ("GH", "GHA", "Gana", "Ghana", "Ghana", "en-GH", "en", "GHS", "volume_play", ["ghana"]),
    ("GR", "GRC", "Grécia", "Greece", "Ελλάδα", "el-GR", "el", "EUR", "medium_value", ["greece", "grecia"]),
    ("GD", "GRD", "Granada", "Grenada", "Grenada", "en-GD", "en", "XCD", "volume_play", ["grenada"]),
    ("GT", "GTM", "Guatemala", "Guatemala", "Guatemala", "es-GT", "es", "GTQ", "volume_play", []),
    ("GN", "GIN", "Guiné", "Guinea", "Guinée", "fr-GN", "fr", "GNF", "volume_play", ["guinea"]),
    ("GW", "GNB", "Guiné-Bissau", "Guinea-Bissau", "Guiné-Bissau", "pt-GW", "pt", "XOF", "volume_play", ["guinea bissau"]),
    ("GY", "GUY", "Guiana", "Guyana", "Guyana", "en-GY", "en", "GYD", "volume_play", ["guyana"]),
    ("HT", "HTI", "Haiti", "Haiti", "Haïti", "fr-HT", "fr", "HTG", "volume_play", []),
    ("HN", "HND", "Honduras", "Honduras", "Honduras", "es-HN", "es", "HNL", "volume_play", []),
    ("HU", "HUN", "Hungria", "Hungary", "Magyarország", "hu-HU", "hu", "HUF", "medium_value", ["hungary"]),
    ("IS", "ISL", "Islândia", "Iceland", "Ísland", "is-IS", "is", "ISK", "high_value", ["iceland", "islandia"]),
    ("IN", "IND", "Índia", "India", "भारत", "hi-IN", "hi", "INR", "volume_play", ["india"]),
    ("ID", "IDN", "Indonésia", "Indonesia", "Indonesia", "id-ID", "id", "IDR", "volume_play", ["indonesia"]),
    ("IR", "IRN", "Irã", "Iran", "ایران", "fa-IR", "fa", "IRR", "volume_play", ["iran", "ira"]),
    ("IQ", "IRQ", "Iraque", "Iraq", "العراق", "ar-IQ", "ar", "IQD", "volume_play", ["iraq"]),
    ("IE", "IRL", "Irlanda", "Ireland", "Éire", "en-IE", "en", "EUR", "high_value", ["ireland"]),
    ("IL", "ISR", "Israel", "Israel", "ישראל", "he-IL", "he", "ILS", "high_value", []),
    ("IT", "ITA", "Itália", "Italy", "Italia", "it-IT", "it", "EUR", "medium_value", ["italy", "italia"]),
    ("JM", "JAM", "Jamaica", "Jamaica", "Jamaica", "en-JM", "en", "JMD", "volume_play", []),
    ("JP", "JPN", "Japão", "Japan", "日本", "ja-JP", "ja", "JPY", "high_value", ["japan", "japao"]),
    ("JO", "JOR", "Jordânia", "Jordan", "الأردن", "ar-JO", "ar", "JOD", "medium_value", ["jordan", "jordania"]),
    ("KZ", "KAZ", "Cazaquistão", "Kazakhstan", "Қазақстан", "kk-KZ", "kk", "KZT", "medium_value", ["kazakhstan", "cazaquistao"]),
    ("KE", "KEN", "Quênia", "Kenya", "Kenya", "sw-KE", "sw", "KES", "volume_play", ["kenya", "quenia"]),
    ("KI", "KIR", "Quiribati", "Kiribati", "Kiribati", "en-KI", "en", "AUD", "volume_play", ["kiribati"]),
    ("KW", "KWT", "Kuwait", "Kuwait", "الكويت", "ar-KW", "ar", "KWD", "medium_value", []),
    ("KG", "KGZ", "Quirguistão", "Kyrgyzstan", "Кыргызстан", "ky-KG", "ky", "KGS", "volume_play", ["kyrgyzstan", "quirguistao"]),
    ("LA", "LAO", "Laos", "Laos", "ລາວ", "lo-LA", "lo", "LAK", "volume_play", []),
    ("LV", "LVA", "Letônia", "Latvia", "Latvija", "lv-LV", "lv", "EUR", "medium_value", ["latvia", "letonia"]),
    ("LB", "LBN", "Líbano", "Lebanon", "لبنان", "ar-LB", "ar", "LBP", "volume_play", ["lebanon", "libano"]),
    ("LS", "LSO", "Lesoto", "Lesotho", "Lesotho", "en-LS", "en", "LSL", "volume_play", ["lesotho"]),
    ("LR", "LBR", "Libéria", "Liberia", "Liberia", "en-LR", "en", "LRD", "volume_play", ["liberia"]),
    ("LY", "LBY", "Líbia", "Libya", "ليبيا", "ar-LY", "ar", "LYD", "volume_play", ["libya", "libia"]),
    ("LI", "LIE", "Liechtenstein", "Liechtenstein", "Liechtenstein", "de-LI", "de", "CHF", "high_value", []),
    ("LT", "LTU", "Lituânia", "Lithuania", "Lietuva", "lt-LT", "lt", "EUR", "medium_value", ["lithuania", "lituania"]),
    ("LU", "LUX", "Luxemburgo", "Luxembourg", "Luxembourg", "fr-LU", "fr", "EUR", "high_value", ["luxembourg"]),
    ("MG", "MDG", "Madagáscar", "Madagascar", "Madagasikara", "fr-MG", "fr", "MGA", "volume_play", ["madagascar"]),
    ("MW", "MWI", "Malawi", "Malawi", "Malawi", "en-MW", "en", "MWK", "volume_play", []),
    ("MY", "MYS", "Malásia", "Malaysia", "Malaysia", "ms-MY", "ms", "MYR", "medium_value", ["malaysia", "malasia"]),
    ("MV", "MDV", "Maldivas", "Maldives", "Maldives", "dv-MV", "dv", "MVR", "medium_value", ["maldives"]),
    ("ML", "MLI", "Mali", "Mali", "Mali", "fr-ML", "fr", "XOF", "volume_play", []),
    ("MT", "MLT", "Malta", "Malta", "Malta", "mt-MT", "mt", "EUR", "medium_value", []),
    ("MH", "MHL", "Ilhas Marshall", "Marshall Islands", "Marshall Islands", "en-MH", "en", "USD", "volume_play", ["marshall islands"]),
    ("MR", "MRT", "Mauritânia", "Mauritania", "موريتانيا", "ar-MR", "ar", "MRU", "volume_play", ["mauritania"]),
    ("MU", "MUS", "Maurício", "Mauritius", "Mauritius", "en-MU", "en", "MUR", "medium_value", ["mauritius", "mauricio"]),
    ("MX", "MEX", "México", "Mexico", "México", "es-MX", "es", "MXN", "medium_value", ["mexico"]),
    ("FM", "FSM", "Micronésia", "Micronesia", "Micronesia", "en-FM", "en", "USD", "volume_play", ["micronesia"]),
    ("MD", "MDA", "Moldávia", "Moldova", "Moldova", "ro-MD", "ro", "MDL", "volume_play", ["moldova", "moldavia"]),
    ("MC", "MCO", "Mônaco", "Monaco", "Monaco", "fr-MC", "fr", "EUR", "high_value", ["monaco"]),
    ("MN", "MNG", "Mongólia", "Mongolia", "Монгол", "mn-MN", "mn", "MNT", "volume_play", ["mongolia"]),
    ("ME", "MNE", "Montenegro", "Montenegro", "Crna Gora", "sr-ME", "sr", "EUR", "volume_play", []),
    ("MA", "MAR", "Marrocos", "Morocco", "المغرب", "ar-MA", "ar", "MAD", "volume_play", ["morocco", "marrocos"]),
    ("MZ", "MOZ", "Moçambique", "Mozambique", "Moçambique", "pt-MZ", "pt", "MZN", "volume_play", ["mozambique", "mocambique"]),
    ("MM", "MMR", "Mianmar", "Myanmar", "မြန်မာ", "my-MM", "my", "MMK", "volume_play", ["myanmar", "mianmar", "burma"]),
    ("NA", "NAM", "Namíbia", "Namibia", "Namibia", "en-NA", "en", "NAD", "volume_play", ["namibia"]),
    ("NR", "NRU", "Nauru", "Nauru", "Nauru", "en-NR", "en", "AUD", "volume_play", []),
    ("NP", "NPL", "Nepal", "Nepal", "नेपाल", "ne-NP", "ne", "NPR", "volume_play", []),
    ("NL", "NLD", "Países Baixos", "Netherlands", "Nederland", "nl-NL", "nl", "EUR", "high_value", ["holanda", "netherlands", "paises baixos"]),
    ("NZ", "NZL", "Nova Zelândia", "New Zealand", "New Zealand", "en-NZ", "en", "NZD", "high_value", ["new zealand"]),
    ("NI", "NIC", "Nicarágua", "Nicaragua", "Nicaragua", "es-NI", "es", "NIO", "volume_play", ["nicaragua"]),
    ("NE", "NER", "Níger", "Niger", "Niger", "fr-NE", "fr", "XOF", "volume_play", ["niger"]),
    ("NG", "NGA", "Nigéria", "Nigeria", "Nigeria", "en-NG", "en", "NGN", "volume_play", ["nigeria"]),
    ("KP", "PRK", "Coreia do Norte", "North Korea", "조선민주주의인민공화국", "ko-KP", "ko", "KPW", "volume_play", ["north korea", "coreia do norte"]),
    ("MK", "MKD", "Macedônia do Norte", "North Macedonia", "Северна Македонија", "mk-MK", "mk", "MKD", "volume_play", ["north macedonia", "macedonia"]),
    ("NO", "NOR", "Noruega", "Norway", "Norge", "nb-NO", "nb", "NOK", "high_value", ["norway"]),
    ("OM", "OMN", "Omã", "Oman", "عُمان", "ar-OM", "ar", "OMR", "medium_value", ["oman", "oma"]),
    ("PK", "PAK", "Paquistão", "Pakistan", "پاکستان", "ur-PK", "ur", "PKR", "volume_play", ["pakistan", "paquistao"]),
    ("PW", "PLW", "Palau", "Palau", "Palau", "en-PW", "en", "USD", "volume_play", []),
    ("PA", "PAN", "Panamá", "Panama", "Panamá", "es-PA", "es", "PAB", "medium_value", ["panama"]),
    ("PG", "PNG", "Papua-Nova Guiné", "Papua New Guinea", "Papua New Guinea", "en-PG", "en", "PGK", "volume_play", ["papua new guinea"]),
    ("PY", "PRY", "Paraguai", "Paraguay", "Paraguay", "es-PY", "es", "PYG", "volume_play", ["paraguay"]),
    ("PE", "PER", "Peru", "Peru", "Perú", "es-PE", "es", "PEN", "volume_play", []),
    ("PH", "PHL", "Filipinas", "Philippines", "Pilipinas", "fil-PH", "fil", "PHP", "volume_play", ["philippines"]),
    ("PL", "POL", "Polônia", "Poland", "Polska", "pl-PL", "pl", "PLN", "medium_value", ["poland", "polonia"]),
    ("PT", "PRT", "Portugal", "Portugal", "Portugal", "pt-PT", "pt", "EUR", "medium_value", []),
    ("QA", "QAT", "Catar", "Qatar", "قطر", "ar-QA", "ar", "QAR", "medium_value", ["qatar", "catar"]),
    ("RO", "ROU", "Romênia", "Romania", "România", "ro-RO", "ro", "RON", "medium_value", ["romania", "romenia"]),
    ("RU", "RUS", "Rússia", "Russia", "Россия", "ru-RU", "ru", "RUB", "medium_value", ["russia", "russia"]),
    ("RW", "RWA", "Ruanda", "Rwanda", "Rwanda", "rw-RW", "rw", "RWF", "volume_play", ["rwanda"]),
    ("KN", "KNA", "São Cristóvão e Névis", "Saint Kitts and Nevis", "Saint Kitts and Nevis", "en-KN", "en", "XCD", "volume_play", ["saint kitts and nevis"]),
    ("LC", "LCA", "Santa Lúcia", "Saint Lucia", "Saint Lucia", "en-LC", "en", "XCD", "volume_play", ["saint lucia"]),
    ("VC", "VCT", "São Vicente e Granadinas", "Saint Vincent and the Grenadines", "Saint Vincent and the Grenadines", "en-VC", "en", "XCD", "volume_play", ["saint vincent and the grenadines"]),
    ("WS", "WSM", "Samoa", "Samoa", "Samoa", "sm-WS", "sm", "WST", "volume_play", []),
    ("SM", "SMR", "San Marino", "San Marino", "San Marino", "it-SM", "it", "EUR", "medium_value", []),
    ("ST", "STP", "São Tomé e Príncipe", "São Tomé and Príncipe", "São Tomé e Príncipe", "pt-ST", "pt", "STN", "volume_play", ["sao tome and principe", "sao tome"]),
    ("SA", "SAU", "Arábia Saudita", "Saudi Arabia", "السعودية", "ar-SA", "ar", "SAR", "medium_value", ["saudi arabia", "arabia saudita"]),
    ("SN", "SEN", "Senegal", "Senegal", "Sénégal", "fr-SN", "fr", "XOF", "volume_play", []),
    ("RS", "SRB", "Sérvia", "Serbia", "Србија", "sr-RS", "sr", "RSD", "volume_play", ["serbia", "servia"]),
    ("SC", "SYC", "Seicheles", "Seychelles", "Seychelles", "fr-SC", "fr", "SCR", "medium_value", ["seychelles"]),
    ("SL", "SLE", "Serra Leoa", "Sierra Leone", "Sierra Leone", "en-SL", "en", "SLE", "volume_play", ["sierra leone"]),
    ("SG", "SGP", "Singapura", "Singapore", "Singapore", "en-SG", "en", "SGD", "high_value", ["singapore"]),
    ("SK", "SVK", "Eslováquia", "Slovakia", "Slovensko", "sk-SK", "sk", "EUR", "medium_value", ["slovakia", "eslovaquia"]),
    ("SI", "SVN", "Eslovênia", "Slovenia", "Slovenija", "sl-SI", "sl", "EUR", "medium_value", ["slovenia", "eslovenia"]),
    ("SB", "SLB", "Ilhas Salomão", "Solomon Islands", "Solomon Islands", "en-SB", "en", "SBD", "volume_play", ["solomon islands"]),
    ("SO", "SOM", "Somália", "Somalia", "Soomaaliya", "so-SO", "so", "SOS", "volume_play", ["somalia"]),
    ("ZA", "ZAF", "África do Sul", "South Africa", "South Africa", "en-ZA", "en", "ZAR", "medium_value", ["south africa", "africa do sul"]),
    ("KR", "KOR", "Coreia do Sul", "South Korea", "대한민국", "ko-KR", "ko", "KRW", "high_value", ["south korea", "coreia"]),
    ("SS", "SSD", "Sudão do Sul", "South Sudan", "South Sudan", "en-SS", "en", "SSP", "volume_play", ["south sudan"]),
    ("ES", "ESP", "Espanha", "Spain", "España", "es-ES", "es", "EUR", "medium_value", ["spain", "espanha"]),
    ("LK", "LKA", "Sri Lanka", "Sri Lanka", "ශ්‍රී ලංකා", "si-LK", "si", "LKR", "volume_play", []),
    ("SD", "SDN", "Sudão", "Sudan", "السودان", "ar-SD", "ar", "SDG", "volume_play", ["sudan", "sudao"]),
    ("SR", "SUR", "Suriname", "Suriname", "Suriname", "nl-SR", "nl", "SRD", "volume_play", []),
    ("SE", "SWE", "Suécia", "Sweden", "Sverige", "sv-SE", "sv", "SEK", "high_value", ["sweden", "suecia"]),
    ("CH", "CHE", "Suíça", "Switzerland", "Schweiz", "de-CH", "de", "CHF", "high_value", ["switzerland", "suica"]),
    ("SY", "SYR", "Síria", "Syria", "سوريا", "ar-SY", "ar", "SYP", "volume_play", ["syria", "siria"]),
    ("TJ", "TJK", "Tajiquistão", "Tajikistan", "Тоҷикистон", "tg-TJ", "tg", "TJS", "volume_play", ["tajikistan", "tajiquistao"]),
    ("TZ", "TZA", "Tanzânia", "Tanzania", "Tanzania", "sw-TZ", "sw", "TZS", "volume_play", ["tanzania"]),
    ("TH", "THA", "Tailândia", "Thailand", "ประเทศไทย", "th-TH", "th", "THB", "medium_value", ["thailand", "tailandia"]),
    ("TL", "TLS", "Timor-Leste", "Timor-Leste", "Timor-Leste", "pt-TL", "pt", "USD", "volume_play", ["timor leste", "east timor"]),
    ("TG", "TGO", "Togo", "Togo", "Togo", "fr-TG", "fr", "XOF", "volume_play", []),
    ("TO", "TON", "Tonga", "Tonga", "Tonga", "en-TO", "en", "TOP", "volume_play", []),
    ("TT", "TTO", "Trindade e Tobago", "Trinidad and Tobago", "Trinidad and Tobago", "en-TT", "en", "TTD", "medium_value", ["trinidad and tobago", "trinidad"]),
    ("TN", "TUN", "Tunísia", "Tunisia", "تونس", "ar-TN", "ar", "TND", "volume_play", ["tunisia", "tunisia"]),
    ("TR", "TUR", "Turquia", "Turkey", "Türkiye", "tr-TR", "tr", "TRY", "medium_value", ["turkey", "turkiye", "turquia"]),
    ("TM", "TKM", "Turcomenistão", "Turkmenistan", "Türkmenistan", "tk-TM", "tk", "TMT", "volume_play", ["turkmenistan", "turcomenistao"]),
    ("TV", "TUV", "Tuvalu", "Tuvalu", "Tuvalu", "en-TV", "en", "AUD", "volume_play", []),
    ("UG", "UGA", "Uganda", "Uganda", "Uganda", "en-UG", "en", "UGX", "volume_play", []),
    ("UA", "UKR", "Ucrânia", "Ukraine", "Україна", "uk-UA", "uk", "UAH", "medium_value", ["ukraine", "ucrania"]),
    ("AE", "ARE", "Emirados Árabes Unidos", "United Arab Emirates", "الإمارات العربية المتحدة", "ar-AE", "ar", "AED", "high_value", ["uae", "emirados", "emirados arabes unidos", "united arab emirates"]),
    ("GB", "GBR", "Reino Unido", "United Kingdom", "United Kingdom", "en-GB", "en", "GBP", "high_value", ["uk", "inglaterra", "england", "great britain", "gra bretanha", "reino unido"]),
    ("US", "USA", "Estados Unidos", "United States", "United States", "en-US", "en", "USD", "high_value", ["eua", "usa", "america", "estados unidos da america", "united states of america"]),
    ("UY", "URY", "Uruguai", "Uruguay", "Uruguay", "es-UY", "es", "UYU", "medium_value", ["uruguay"]),
    ("UZ", "UZB", "Uzbequistão", "Uzbekistan", "Oʻzbekiston", "uz-UZ", "uz", "UZS", "volume_play", ["uzbekistan", "uzbequistao"]),
    ("VU", "VUT", "Vanuatu", "Vanuatu", "Vanuatu", "bi-VU", "bi", "VUV", "volume_play", []),
    ("VA", "VAT", "Vaticano", "Vatican City", "Città del Vaticano", "it-VA", "it", "EUR", "medium_value", ["vatican", "vatican city", "holy see", "santa se", "santa sé"]),
    ("VE", "VEN", "Venezuela", "Venezuela", "Venezuela", "es-VE", "es", "VES", "volume_play", []),
    ("VN", "VNM", "Vietnã", "Vietnam", "Việt Nam", "vi-VN", "vi", "VND", "volume_play", ["vietnam", "vietna"]),
    ("YE", "YEM", "Iêmen", "Yemen", "اليمن", "ar-YE", "ar", "YER", "volume_play", ["yemen", "iemen"]),
    ("ZM", "ZMB", "Zâmbia", "Zambia", "Zambia", "en-ZM", "en", "ZMW", "volume_play", ["zambia"]),
    ("ZW", "ZWE", "Zimbábue", "Zimbabwe", "Zimbabwe", "en-ZW", "en", "ZWL", "volume_play", ["zimbabwe"]),
    ("PS", "PSE", "Palestina", "Palestine", "فلسطين", "ar-PS", "ar", "ILS", "volume_play", ["palestina", "state of palestine"]),
]


def flag_emoji(iso2: str) -> str:
    """Regional-indicator flag emoji derived from the ISO-2 code."""
    iso2 = (iso2 or "").upper()
    if len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in iso2)


def _strip(text: str) -> str:
    norm = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").strip().lower()


def _build() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for iso2, iso3, pt, en, native, locale, lang2, currency, tier, extra in _RAW:
        auto_aliases = {iso2.lower(), iso3.lower(), _strip(pt), _strip(en), _strip(native)}
        aliases = sorted({_strip(a) for a in [*extra]} | auto_aliases)
        out.append(
            {
                "country_code": iso2,
                "iso3": iso3,
                "country_name": pt,
                "name_en": en,
                "name_native": native,
                "native_language": locale,
                "language_code": lang2,
                "language_short": lang2,
                "language_constant": LANGUAGE_CONSTANTS.get(lang2),
                "google_ads_geo_target": GEO_TARGETS.get(iso2),
                "currency_code": currency,
                "market_tier": tier,
                "flag_emoji": flag_emoji(iso2),
                "aliases": aliases,
                "is_active": True,
                "is_sovereign": True,
            }
        )
    return out


COUNTRIES: List[Dict[str, Any]] = _build()

# --- lookup indices -----------------------------------------------------------
_BY_CODE: Dict[str, Dict[str, Any]] = {c["country_code"]: c for c in COUNTRIES}
_BY_ISO3: Dict[str, Dict[str, Any]] = {c["iso3"]: c for c in COUNTRIES}
_BY_KEY: Dict[str, Dict[str, Any]] = {}
for c in COUNTRIES:
    for key in [c["country_code"], c["iso3"], c["country_name"], c["name_en"], c["name_native"], *c["aliases"]]:
        _BY_KEY.setdefault(_strip(key), c)


def resolve_country(query: Optional[str] = None, code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve a country by ISO2, ISO3, PT/EN/native name, or alias
    (accent- and case-insensitive). `code` (ISO2/ISO3) is tried first."""
    if code:
        c = (code or "").strip().upper()
        hit = _BY_CODE.get(c) or _BY_ISO3.get(c)
        if hit:
            return hit
        hit = _BY_KEY.get(_strip(code))
        if hit:
            return hit
    if query:
        return _BY_KEY.get(_strip(query))
    return None


def fallback_countries() -> List[Dict[str, Any]]:
    """The 195 active sovereign countries (used as the API/UI fallback)."""
    return [
        {
            "country_code": c["country_code"],
            "country_name": c["country_name"],
            "native_language": c["native_language"],
            "market_tier": c["market_tier"],
            "flag_emoji": c["flag_emoji"],
            "is_active": True,
        }
        for c in COUNTRIES
    ]
