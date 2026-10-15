-- GAQL extraídas VERBATIM (sintaxe gaarf: AS alias, :campo aninhado, ~N, {macro}).
-- Data 2026-10-14. Conferência: catálogo do servidor v25 do VOLC (volc_ads/google_ads_api/catalogo_gaql_v25.json).
-- O catálogo NÃO tem selectable_with: compatibilidade campo×FROM só se prova com validate_only (pesquisador A).

-- ===== ORIGEM: google-marketing-solutions/negative_keyword_cleaner@e3443326691b627013e9beae91f09b5646108ff7:src/utils/gaarf_queries.py:43-172
-- campos fora do catálogo v25: nenhum
  def __init__(self) -> None:
    self.query_text = """
            SELECT
                customer_client.id,
                customer_client.descriptive_name
            FROM customer_client
            WHERE
                customer_client.manager = FALSE AND
                customer_client.status = 'ENABLED' AND
                customer.status = 'ENABLED'
        """


class AdgroupNegativeKeywords(BaseQuery):
  """Class for querying ad group negative keywords.

  This class extends BaseQuery to execute a SQL query that selects details of
  negative keywords
  at the ad group level, including the criterion ID, keyword text, match type,
  and other relevant information.
  """

  def __init__(self) -> None:
    self.query_text = f"""
            SELECT
                ad_group_criterion.criterion_id AS criterion_id,
                ad_group_criterion.keyword.text AS keyword,
                ad_group_criterion.negative AS is_negative,
                ad_group_criterion.keyword.match_type AS match_type,
                '{KeywordLevel.ADGROUP.value}' AS level,
                ad_group.id AS adgroup_id,
                ad_group.name AS adgroup_name,
                campaign.id AS campaign_id,
                campaign.name AS campaign_name,
                customer.id AS account_id,
                customer.descriptive_name AS account_name
            FROM ad_group_criterion
            WHERE
                ad_group_criterion.type = 'KEYWORD' AND
                ad_group_criterion.negative = True AND
                campaign.status = 'ENABLED' AND
                ad_group.status = 'ENABLED'
        """


class CampaignNegativeKeywords(BaseQuery):

  def __init__(self) -> None:
    self.query_text = f"""
            SELECT
                campaign_criterion.criterion_id AS criterion_id,
                campaign_criterion.keyword.text AS keyword,
                campaign_criterion.negative AS is_negative,
                campaign_criterion.keyword.match_type AS match_type,
                '{KeywordLevel.CAMPAIGN.value}' AS level,
                '' AS adgroup_id,
                '' AS adgroup_name,
                campaign.id AS campaign_id,
                campaign.name AS campaign_name,
                customer.id AS account_id,
                customer.descriptive_name AS account_name
            FROM campaign_criterion
            WHERE
                campaign_criterion.negative = True AND
                campaign_criterion.type = 'KEYWORD' AND
                campaign.status = 'ENABLED'
        """


class PositiveKeywords(BaseQuery):
  """Class for querying positive keywords.

  This class extends BaseQuery to execute a SQL query that selects details of
  positive keywords
  at the ad group level, including the criterion ID, keyword text, match type,
  and other relevant information.
  """

  def __init__(self) -> None:
    self.query_text = f"""
            SELECT
                ad_group_criterion.criterion_id AS criterion_id,
                ad_group_criterion.keyword.text AS keyword,
                ad_group_criterion.negative AS is_negative,
                ad_group_criterion.keyword.match_type AS match_type,
                '{KeywordLevel.ADGROUP.value}' AS level,
                ad_group.id AS adgroup_id,
                ad_group.name AS adgroup_name,
                campaign.id AS campaign_id,
                campaign.name AS campaign_name,
                customer.id AS account_id,
                customer.descriptive_name AS account_name
            FROM ad_group_criterion
            WHERE
                ad_group_criterion.type = 'KEYWORD' AND
                ad_group_criterion.negative = False AND
                campaign.status = 'ENABLED' AND
                ad_group.status = 'ENABLED'
        """


class AccountNegativeKeywords(BaseQuery):
  """Class for querying account level negative keywords.

  This class extends BaseQuery to execute a SQL query that selects details of
  negative keywords
  at the account level, including shared set ID, keyword text, match type, and
  other related information.
  """

  def __init__(self) -> None:
    self.query_text = f"""
            SELECT
                shared_criterion.criterion_id AS criterion_id,
                shared_criterion.keyword.text AS keyword,
                'True' AS is_negative,
                shared_criterion.keyword.match_type AS match_type,
                '{KeywordLevel.ACCOUNT.value}' AS level,
                '' AS adgroup_id,
                '' AS adgroup_name,
                '' AS campaign_id,
                shared_set.name AS campaign_name,
                customer.id AS account_id,
                customer.descriptive_name AS account_name
            FROM
                shared_criterion
            WHERE
                shared_set.type = 'NEGATIVE_KEYWORDS' AND
                shared_set.status = 'ENABLED'
        """

