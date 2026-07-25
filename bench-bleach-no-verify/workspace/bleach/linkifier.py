"""Bleach linkifier.

Provides the linkify() function and Linker class for converting
URL-like text into clickable HTML links.
"""

import re

from bleach.callbacks import DEFAULT_CALLBACKS


#: Regular expression for matching email addresses
EMAIL_RE = re.compile(
    r"""(?<!["'=/:?.,\w])
        (?:mailto:)?
        (
            [\w.!#$%&'*+/=?^_`{|}~-]+
            @
            [\w-]+(?:\.[\w-]+)+
        )
        (?![/\w.])""",
    re.IGNORECASE | re.VERBOSE,
)


#: Regular expression fragment for the TLD part of a URL
TLDS = (
    'aaa|aarp|abarth|abb|abbott|abbvie|abc|able|abogado|abudhabi|'
    'ac|academy|accenture|accountant|accountants|aco|actor|ad|adac|ads|'
    'adult|ae|aeg|aero|aetna|af|afl|ag|agakhan|agency|ai|aig|airbus|'
    'airforce|airtel|akdn|al|alfaromeo|alibaba|alipay|allfinanz|allstate|'
    'ally|alsace|alstom|am|amex|amsterdam|analytics|android|ao|aol|'
    'apartments|app|apple|aq|aquarelle|ar|arab|aramco|archi|army|arpa|'
    'art|arte|as|asia|associates|at|athleta|attorney|au|auction|audi|'
    'audio|auspost|author|auto|autos|avianca|aw|aws|ax|axa|az|azure|'
    'ba|baby|baidu|banamex|bananarepublic|band|bank|bar|barcelona|'
    'barclaycard|barclays|barefoot|bargains|baseball|basketball|bauhaus|'
    'bayern|bb|bbc|bbt|bbva|bcg|bcn|bd|be|beats|beauty|beer|bentley|'
    'berlin|best|bestbuy|bet|bf|bg|bh|bharti|bi|bible|bid|bike|bing|'
    'bingo|bio|biz|bj|black|blackfriday|blockbuster|blog|bloomberg|blue|'
    'bm|bms|bmw|bn|bnpparibas|bo|boats|boehringer|bofa|bom|bond|boo|'
    'book|booking|bosch|bostik|boston|bot|boutique|box|br|bradesco|'
    'bridgestone|broadway|broker|brother|brussels|bs|bt|budapest|bugatti|'
    'build|builders|business|buy|buzz|bv|bw|by|bz|bzh|ca|cab|cafe|cal|'
    'call|calvinklein|cam|camera|camp|cancerresearch|canon|capetown|'
    'capital|capitalone|car|caravan|cards|care|career|careers|cars|'
    'casa|case|cash|casino|cat|catering|catholic|cba|cbn|cbre|cbs|cc|'
    'cd|center|ceo|cern|cf|cfa|cfd|cg|ch|chanel|channel|charity|chase|'
    'chat|cheap|chintai|christmas|chrome|church|ci|cipriani|circle|'
    'cisco|citadel|citi|citic|city|cityeats|ck|cl|claims|cleaning|click|'
    'clinic|clinique|clothing|cloud|club|clubmed|cm|cn|co|coach|codes|'
    'coffee|college|cologne|com|comcast|commbank|community|company|'
    'compare|computer|comsec|condos|construction|consulting|contact|'
    'contractors|cooking|cookingchannel|cool|coop|corsica|country|coupon|'
    'coupons|courses|cpa|cr|credit|creditcard|creditunion|cricket|crown|'
    'crs|cruise|cruises|cu|cuisinella|cv|cw|cx|cy|cymru|cyou|cz|dabur|'
    'dad|dance|data|date|dating|datsun|day|dclk|dds|de|deal|dealer|'
    'deals|degree|delivery|dell|deloitte|delta|democrat|dental|dentist|'
    'desi|design|dev|dhl|diamonds|diet|digital|direct|directory|discount|'
    'discover|dish|diy|dj|dk|dm|dnp|do|docs|doctor|dog|domains|dot|'
    'download|drive|dtv|dubai|dunlop|dupont|durban|dvag|dvr|dz|earth|'
    'eat|ec|eco|edeka|edu|education|ee|eg|email|emerck|energy|engineer|'
    'engineering|enterprises|epson|equipment|er|ericsson|erni|es|esq|'
    'estate|et|etisalat|eu|eurovision|eus|events|exchange|expert|exposed|'
    'express|extraspace|fage|fail|fairwinds|faith|family|fan|fans|farm|'
    'farmers|fashion|fast|fedex|feedback|ferrari|ferrero|fi|fiat|'
    'fidelity|fido|film|final|finance|financial|fire|firestone|firmdale|'
    'fish|fishing|fit|fitness|fj|fk|flickr|flights|flir|florist|flowers|'
    'fly|fm|fo|foo|food|foodnetwork|football|ford|forex|forsale|forum|'
    'foundation|fox|fr|free|fresenius|frl|frogans|frontdoor|frontier|'
    'ftr|fujitsu|fun|fund|furniture|futbol|fyi|ga|gal|gallery|gallo|'
    'gallup|game|games|gap|garden|gay|gb|gbiz|gd|gdn|ge|gea|gent|'
    'genting|george|gf|gg|ggee|gh|gi|gift|gifts|gives|giving|gl|glass|'
    'gle|global|globo|gm|gmail|gmbh|gmo|gmx|gn|godaddy|gold|goldpoint|'
    'golf|goo|goodyear|goog|google|gop|got|gov|gp|gq|gr|grainger|'
    'graphics|gratis|green|gripe|grocery|group|gs|gt|gu|guardian|'
    'gucci|guge|guide|guitars|guru|gw|gy|hair|hamburg|hangout|haus|'
    'hbo|hdfc|hdfcbank|health|healthcare|help|helsinki|here|hermes|'
    'hermesparis|hiphop|hisamitsu|hitachi|hiv|hk|hkt|hm|hn|hockey|'
    'holdings|holiday|homedepot|homegoods|homes|homesense|honda|horse|'
    'hospital|host|hosting|hot|hoteles|hotmail|house|how|hr|hsbc|ht|'
    'hu|hughes|hyatt|hyundai|ibm|icbc|ice|icu|id|ie|ieee|ifm|ikano|'
    'il|im|imamat|imdb|immo|immobilien|in|inc|industries|infiniti|info|'
    'ing|ink|institute|insurance|insure|int|international|intuit|'
    'investments|io|ipiranga|iq|ir|irish|is|ismaili|ist|istanbul|it|'
    'itau|itv|jaguar|java|jcb|je|jeep|jetzt|jewelry|jio|jll|jm|jmp|jnj|'
    'jo|jobs|joburg|jot|joy|jp|jpmorgan|jprs|juegos|juniper|kaufen|kddi|'
    'ke|kerryhotels|kerrylogistics|kerryproperties|kfh|kg|kh|ki|kia|kids|'
    'kim|kinder|kindle|kitchen|kiwi|km|kn|koeln|komatsu|kosher|kp|kpmg|'
    'kpn|kr|krd|kred|kuokgroup|kw|ky|kyoto|kz|la|lacaixa|lamborghini|'
    'lamer|lancaster|lancia|land|landrover|lanxess|lasalle|lat|latino|'
    'latrobe|law|lawyer|lb|lc|lds|lease|leclerc|lefrak|legal|lego|lexus|'
    'lgbt|li|lidl|life|lifeinsurance|lifestyle|lighting|like|lilly|'
    'limited|limo|lincoln|linde|link|lipsy|live|living|llc|llp|loan|'
    'loans|locker|locus|loft|lol|london|lotte|lotus|love|lpl|lplfinancial|'
    'lr|ls|lt|ltd|lu|lundbeck|luxe|luxury|lv|ly|ma|madrid|maif|'
    'maison|makeup|man|management|mango|map|market|marketing|markets|'
    'marriott|marshalls|maserati|mattel|mba|mc|mckinsey|md|me|med|media|'
    'meet|melbourne|meme|memorial|men|menu|merckmsd|mg|mh|miami|'
    'microsoft|mil|mini|mint|mit|mitsubishi|mk|ml|mlb|mls|mm|mma|mn|'
    'mo|mobi|mobile|moda|moe|moi|mom|monash|money|monster|mormon|'
    'mortgage|moscow|moto|motorcycles|mov|movie|mp|mq|mr|ms|msd|mt|mtn|'
    'mtr|mu|museum|music|mutual|mv|mw|mx|my|mz|na|nab|nagoya|name|'
    'natura|navy|nba|nc|ne|nec|net|netbank|netflix|network|neustar|new|'
    'news|next|nextdirect|nexus|nf|nfl|ng|ngo|nhk|ni|nico|nike|nikon|'
    'ninja|nissan|nissay|nl|no|nokia|northwesternmutual|norton|now|'
    'nowruz|nowtv|np|nr|nra|nrw|ntt|nu|nyc|nz|obi|observer|office|'
    'okinawa|olayan|olayangroup|oldnavy|ollo|om|omega|one|ong|onl|'
    'online|ooo|open|oracle|orange|org|organic|origins|osaka|otsuka|ott|'
    'ovh|pa|page|panasonic|paris|pars|partners|parts|party|passagens|'
    'pay|pccw|pe|pet|pf|pfizer|pg|ph|pharmacy|phd|philips|phone|photo|'
    'photography|photos|physio|pics|pictet|pictures|pid|pin|ping|pink|'
    'pioneer|pizza|pk|pl|place|play|playstation|plumbing|plus|pm|pn|pnc|'
    'pohl|poker|politie|porn|post|pr|pramerica|praxi|press|prime|pro|'
    'prod|productions|prof|progressive|promo|properties|property|'
    'protection|pru|prudential|ps|pt|pub|pw|pwc|py|qa|qpon|quebec|quest|'
    'racing|radio|re|read|realestate|realtor|realty|recipes|red|'
    'redstone|redumbrella|rehab|reise|reisen|reit|reliance|ren|rent|'
    'rentals|repair|report|republican|rest|restaurant|review|reviews|'
    'rexroth|rich|richardli|ricoh|ril|rio|rip|ro|rocher|rocks|rodeo|'
    'rogers|room|rs|rsvp|ru|rugby|ruhr|run|rw|rwe|ryukyu|sa|saarland|'
    'safe|safety|sakura|sale|salon|samsclub|samsung|sandvik|sandvikcoromant|'
    'sanofi|sap|sarl|sas|save|saxo|sb|sbi|sbs|sc|sca|scb|schaeffler|'
    'schmidt|scholarships|school|schule|schwarz|science|scot|sd|se|search|'
    'seat|secure|security|seek|select|sener|services|ses|seven|sew|sex|'
    'sexy|sfr|sg|sh|shangrila|sharp|shaw|shell|shia|shiksha|shoes|shop|'
    'shopping|shouji|show|showtime|si|silk|sina|singles|site|sj|sk|ski|'
    'skin|sky|skype|sl|sling|sm|smart|smile|sn|sncf|so|soccer|social|'
    'softbank|software|sohu|solar|solutions|song|sony|soy|spa|space|'
    'sport|spot|sr|srl|ss|st|stada|staples|star|statebank|statefarm|'
    'stc|stcgroup|stockholm|storage|store|stream|studio|study|style|su|'
    'sucks|supplies|supply|support|surf|surgery|suzuki|sv|swatch|swiss|'
    'sx|sy|sydney|systems|sz|tab|taipei|talk|taobao|target|tatamotors|'
    'tatar|tattoo|tax|taxi|tc|tci|td|tdk|team|tech|technology|tel|'
    'temasek|tennis|teva|tf|tg|th|thd|theater|theatre|tiaa|tickets|'
    'tienda|tiffany|tips|tires|tirol|tj|tjmaxx|tjx|tk|tkmaxx|tl|tm|'
    'tmall|tn|to|today|tokyo|tools|top|toray|toshiba|total|tours|town|'
    'toyota|toys|tr|trade|trading|training|travel|travelchannel|travelers|'
    'travelersinsurance|trust|trv|tt|tube|tui|tunes|tushu|tv|tvs|tw|tz|'
    'ua|ubank|ubs|ug|uk|unicom|university|uno|uol|ups|us|uy|uz|va|'
    'vacations|vana|vanguard|vc|ve|vegas|ventures|verisign|versicherung|'
    'vet|vg|vi|viajes|video|vig|viking|villas|vin|vip|virgin|visa|vision|'
    'viva|vivo|vlaanderen|vn|vodka|volkswagen|volvo|vote|voting|voto|'
    'voyage|vu|vuelos|wales|walmart|walter|wang|wanggou|watch|watches|'
    'weather|weatherchannel|webcam|weber|website|wed|wedding|weibo|weir|'
    'wf|whoswho|wien|wiki|williamhill|win|windows|wine|winners|wme|'
    'wolterskluwer|woodside|work|works|world|wow|ws|wtc|wtf|xbox|xerox|'
    'xfinity|xihuan|xin|xxx|xyz|yachts|yahoo|yamaxun|yandex|ye|'
    'yodobashi|yoga|yokohama|you|youtube|yt|yun|za|zappos|zara|zero|zip|'
    'zm|zone|zuerich|zw'
)


def build_url_re(tlds=TLDS, parse_email=False):
    """Build a compiled regex for matching URLs in text.

    Args:
        tlds: A pipe-delimited string of TLDs to match.
        parse_email: Whether to include email matching.

    Returns:
        A compiled regex object that matches URLs (and optionally emails).
    """
    # Build protocol part
    protocol = r'(?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)'

    # Build URL pattern
    url_pattern = (
        r'(?<!["\':;.,=?!])'
        r'\b'
        r'(?:'
        r'(?:%(proto)s)'
        r'(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+'
        r'(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|'
        r'[^\s`!()\[\]{};:\'\".,<>?\xab\xbb\u201c\u201d\u2018\u2019])'
        r')'
    ) % {'proto': protocol}

    url_re = re.compile(url_pattern, re.IGNORECASE | re.VERBOSE)

    if parse_email:
        # Return a combined regex that matches both URLs and emails
        combined = re.compile(
            '(%s|%s)' % (url_pattern, EMAIL_RE.pattern),
            re.IGNORECASE | re.VERBOSE,
        )
        return combined

    return url_re


#: Pre-compiled URL regex using the default TLD list
URL_RE = build_url_re()


class Linker:
    """Converts URL-like text in a string into HTML links."""

    def __init__(self, callbacks=None, url_re=None, parse_email=False,
                 skip_tags=None, recognized_tags=None):
        self.callbacks = callbacks if callbacks is not None else DEFAULT_CALLBACKS
        self.url_re = url_re if url_re is not None else URL_RE
        self.parse_email = parse_email
        self.skip_tags = skip_tags or []
        self.recognized_tags = recognized_tags or []

    def linkify(self, text):
        """Convert URLs in text to HTML links.

        Args:
            text: The plain text to linkify.

        Returns:
            The text with URLs converted to <a> links.
        """
        if not text:
            return text

        # If text contains HTML tags, handle them accordingly
        if self._contains_html(text):
            return self._linkify_html(text)

        return self._linkify_text(text)

    def _contains_html(self, text):
        """Check if text contains HTML tags."""
        return bool(re.search(r'<[^>]+>', text))

    def _linkify_text(self, text):
        """Linkify plain text (no existing HTML)."""
        # First linkify emails if parse_email is True
        if self.parse_email:
            text = self._linkify_emails(text)

        def replace(match):
            url = match.group(0)
            href = url
            if not re.match(r'^[a-z][\w-]+:', href):
                href = 'http://' + href
            attrs = {'href': href}

            # Apply callbacks
            for cb in self.callbacks:
                attrs = cb(attrs) or attrs

            # Build the link tag
            attr_str = ''.join(
                ' %s="%s"' % (k, v) for k, v in attrs.items()
            )
            return '<a%s>%s</a>' % (attr_str, url)

        return self.url_re.sub(replace, text)

    def _linkify_emails(self, text):
        """Linkify email addresses in text."""
        def replace(match):
            email = match.group(0)
            if email.startswith('mailto:'):
                href = email
                display = email[7:]  # Remove 'mailto:' prefix
            else:
                href = 'mailto:' + email
                display = email
            attrs = {'href': href}
            for cb in self.callbacks:
                attrs = cb(attrs) or attrs
            attr_str = ''.join(
                ' %s="%s"' % (k, v) for k, v in attrs.items()
            )
            return '<a%s>%s</a>' % (attr_str, display)

        return EMAIL_RE.sub(replace, text)

    def _linkify_html(self, text):
        """Linkify text that contains existing HTML.

        Skips linkification inside <a> tags and skip_tags.
        """
        # Simple approach: split by HTML tags, linkify text between tags
        parts = re.split(r'(<[^>]+>)', text)
        result = []
        skip_stack = []  # stack of tag names we are currently inside
        # Tags that should block linkification for their content
        skip_tags_set = set(self.skip_tags) | {'a'}

        for part in parts:
            if part.startswith('<'):
                # Check if this is a closing tag
                close_match = re.match(r'<\s*/\s*(\w+)', part)
                if close_match:
                    tag_name = close_match.group(1).lower()
                    if skip_stack and skip_stack[-1] == tag_name:
                        skip_stack.pop()
                else:
                    # Check if this is an opening/self-closing tag
                    open_match = re.match(r'<\s*(\w+)', part)
                    if open_match:
                        tag_name = open_match.group(1).lower()
                        if tag_name in skip_tags_set and not re.search(r'/\s*>$', part):
                            skip_stack.append(tag_name)

                result.append(part)
            else:
                if skip_stack:
                    # We're inside a skip tag, don't linkify
                    result.append(part)
                else:
                    result.append(self._linkify_text(part))
        return ''.join(result)


def linkify(text, callbacks=None, parse_email=False, skip_tags=None,
            recognized_tags=None):
    """Convert URLs in text to HTML links.

    Convenience function that creates a Linker and calls linkify().

    Args:
        text: The plain text to linkify.
        callbacks: Optional list of callback functions.
        parse_email: Whether to parse email addresses.
        skip_tags: List of tags to skip linkification within.
        recognized_tags: List of additional recognized tags.

    Returns:
        The text with URLs converted to HTML links.
    """
    linker = Linker(
        callbacks=callbacks,
        parse_email=parse_email,
        skip_tags=skip_tags,
        recognized_tags=recognized_tags,
    )
    return linker.linkify(text)
