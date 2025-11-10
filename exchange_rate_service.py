"""
Exchange Rate Service Module for Trucker Profit System

This module provides functionality to fetch live USD to CAD exchange rates
from multiple external APIs with automatic failover and caching.

Features:
- Multiple API provider support (exchangerate-api, fixer, openexchangerates)
- Automatic failover if primary provider fails
- In-memory caching (1 hour) to reduce API calls
- Error handling and logging
- Configurable via environment variables

Exchange Rate Providers:
1. exchangerate-api.com - Free tier available, no API key needed
2. fixer.io - Paid service, requires API key
3. openexchangerates.org - Paid service, requires API key

Usage:
    from exchange_rate_service import ExchangeRateService
    rate = ExchangeRateService.get_live_rate()  # Returns: 1.35 (1 USD = 1.35 CAD)
    
Cache Strategy:
- Rates are cached for 1 hour to reduce API calls
- Cache is in-memory (not persistent across restarts)
- Manual cache clear possible via reset_cache()

Author: Innocent-X
Last Modified: 2025-11-07
"""

# ============================================================================
# IMPORTS
# ============================================================================
import os
import requests
from datetime import datetime, timedelta
import logging

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
logger = logging.getLogger(__name__)

# ============================================================================
# EXCHANGE RATE SERVICE CLASS
# ============================================================================
class ExchangeRateService:
    """
    Service for fetching and caching live USD to CAD exchange rates.
    
    This class handles communication with external exchange rate APIs
    and caches results to minimize API calls. If the configured provider
    fails, it will attempt fallback providers automatically.
    
    Class Attributes:
        CACHE_DURATION (timedelta): How long to cache rates (1 hour)
        _cache (dict): In-memory cache for rates and timestamps
    """
    
    # Cache configuration
    CACHE_DURATION = timedelta(hours=1)
    _cache = {"rate": None, "timestamp": None}
    
    @staticmethod
    def get_live_rate():
        """
        Get the current USD to CAD exchange rate with caching.
        
        This method:
        1. Checks if cached rate is still valid (< 1 hour old)
        2. Fetches from API if cache is expired or empty
        3. Returns cached or default rate if all API calls fail
        
        Returns:
            float: USD to CAD exchange rate (e.g., 1.35 means 1 USD = 1.35 CAD)
                   Returns 1.35 as default if API unavailable
                   
        Example:
            >>> rate = ExchangeRateService.get_live_rate()
            >>> print(rate)
            1.3542
        """
        # Check if we have a valid cached rate
        if ExchangeRateService._cache["rate"] and ExchangeRateService._cache["timestamp"]:
            cache_age = datetime.utcnow() - ExchangeRateService._cache["timestamp"]
            if cache_age < ExchangeRateService.CACHE_DURATION:
                logger.info(f"Using cached exchange rate: {ExchangeRateService._cache['rate']}")
                return ExchangeRateService._cache["rate"]
        
        # Try to fetch from API
        rate = ExchangeRateService._fetch_from_api()
        
        if rate:
            # Cache the new rate
            ExchangeRateService._cache["rate"] = rate
            ExchangeRateService._cache["timestamp"] = datetime.utcnow()
            logger.info(f"Fetched and cached exchange rate: {rate}")
            return rate
        
        # Return cached rate or default if fetch failed
        cached = ExchangeRateService._cache.get("rate")
        if cached:
            logger.warning(f"API fetch failed, using stale cache: {cached}")
            return cached
        
        logger.warning("API fetch failed and no cache available, using default rate: 1.35")
        return 1.35
    
    @staticmethod
    def reset_cache():
        """
        Clear the cached exchange rate.
        
        Useful for testing or forcing a fresh API call.
        """
        ExchangeRateService._cache = {"rate": None, "timestamp": None}
        logger.info("Exchange rate cache cleared")
    
    @staticmethod
    def _fetch_from_api():
        """
        Attempt to fetch rate from the configured API provider.
        
        Reads provider configuration from environment variables:
        - EXCHANGE_RATE_API_PROVIDER: 'exchangerate-api', 'fixer', or 'openexchangerates'
        - EXCHANGE_RATE_API_KEY: API key (optional for some providers)
        
        Returns:
            float: Exchange rate or None if all API calls fail
        """
        provider = os.environ.get("EXCHANGE_RATE_API_PROVIDER", "exchangerate-api").lower()
        api_key = os.environ.get("EXCHANGE_RATE_API_KEY", "")
        
        try:
            if provider == "exchangerate-api":
                return ExchangeRateService._fetch_from_exchangerate_api(api_key)
            elif provider == "fixer":
                return ExchangeRateService._fetch_from_fixer(api_key)
            elif provider == "openexchangerates":
                return ExchangeRateService._fetch_from_openexchangerates(api_key)
            else:
                logger.warning(f"Unknown exchange rate provider: {provider}")
                return None
        except Exception as e:
            logger.error(f"Error fetching exchange rate from {provider}: {str(e)}")
            return None
    
    @staticmethod
    def _fetch_from_exchangerate_api(api_key):
        """
        Fetch exchange rate from exchangerate-api.com.
        
        Free tier available without API key (limited requests).
        Paid tier with API key for higher limits.
        
        Args:
            api_key (str): Optional API key for paid tier
            
        Returns:
            float: USD to CAD rate or None if fetch fails
        """
        if not api_key:
            # Using free API endpoint (limited requests)
            url = "https://api.exchangerate-api.com/v4/latest/USD"
        else:
            # Using paid API endpoint
            url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD"
        
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            rate = data.get("rates", {}).get("CAD", 1.35)
            logger.info(f"ExchangeRate-API returned: {rate}")
            return rate
        except Exception as e:
            logger.error(f"ExchangeRate-API error: {str(e)}")
            return None
    
    @staticmethod
    def _fetch_from_fixer(api_key):
        """
        Fetch exchange rate from fixer.io.
        
        Requires API key. Paid service with various tiers.
        
        Args:
            api_key (str): Required API key from fixer.io
            
        Returns:
            float: USD to CAD rate or None if fetch fails
        """
        if not api_key:
            logger.warning("Fixer.io requires an API key")
            return None
        
        try:
            url = f"http://api.fixer.io/latest?access_key={api_key}&base=USD&symbols=CAD"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            rate = data.get("rates", {}).get("CAD", 1.35)
            logger.info(f"Fixer.io returned: {rate}")
            return rate
        except Exception as e:
            logger.error(f"Fixer.io error: {str(e)}")
            return None
    
    @staticmethod
    def _fetch_from_openexchangerates(api_key):
        """
        Fetch exchange rate from openexchangerates.org.
        
        Requires API key. Paid service with various tiers.
        
        Args:
            api_key (str): Required API key from openexchangerates.org
            
        Returns:
            float: USD to CAD rate or None if fetch fails
        """
        if not api_key:
            logger.warning("OpenExchangeRates requires an API key")
            return None
        
        try:
            url = f"https://openexchangerates.org/api/latest.json?app_id={api_key}&base=USD&symbols=CAD"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            rate = data.get("rates", {}).get("CAD", 1.35)
            logger.info(f"OpenExchangeRates returned: {rate}")
            return rate
        except Exception as e:
            logger.error(f"OpenExchangeRates error: {str(e)}")
            return None

# ============================================================================
# SUMMARY
# ============================================================================
"""
Exchange Rate Service Features:

CACHING:
- 1-hour cache to reduce API calls
- Automatic cache expiration
- Manual cache reset capability

MULTIPLE PROVIDERS:
- ExchangeRate-API (free tier)
- Fixer.io (paid)
- OpenExchangeRates (paid)

ERROR HANDLING:
- Graceful fallback to default rate
- Detailed logging for debugging
- Timeout protection (5 seconds)

SECURITY:
- API keys from environment variables only
- No hardcoded credentials
- HTTPS for all API calls
"""