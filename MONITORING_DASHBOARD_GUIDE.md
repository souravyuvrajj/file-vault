# Grafana Dashboard Guide for Application Monitoring

This guide provides instructions and example PromQL queries for setting up Grafana dashboards to monitor your application using metrics collected by Prometheus via `django-prometheus`. It focuses on visualizing the "Four Golden Signals": Traffic, Errors, Latency, and Saturation.

## Prerequisites

1.  Prometheus is successfully scraping metrics from your Django application (available at `/metrics`).
2.  Grafana is installed and running.
3.  You have added Prometheus as a data source in Grafana (typically at `http://prometheus:9090` from Grafana's perspective if running in the same Docker network).

## General Steps for Adding Panels in Grafana

1.  **Navigate to your Grafana instance** (e.g., `http://localhost:3001`).
2.  **Create a new Dashboard** or open an existing one:
    *   Click the `+` icon on the left sidebar, then "Dashboard".
    *   Click "Add new panel" (or "Add panel" on an existing dashboard).
3.  **Select your Prometheus Data Source** from the dropdown (e.g., "Prometheus").
4.  **Enter a PromQL Query**: In the "Metrics browser" or query editor section of the panel (often labeled "A"), type your PromQL query.
5.  **Choose Visualization**: On the right-hand panel, select an appropriate visualization type (e.g., "Time series", "Stat", "Gauge", "Table").
6.  **Customize Panel**: Adjust titles, legends, axes, units, thresholds, etc., under the "Panel" options on the right.
7.  **Apply Changes and Save**: Click "Apply" to see the panel, then save the panel and the dashboard.

---

## Visualizing The Four Golden Signals

Here are example PromQL queries and visualization suggestions for each signal. Remember that `django-prometheus` prefixes most of its metrics with `django_`.

### 1. Traffic

Measures the volume of requests and activity in your application.

*   **Overall Request Rate (Requests per second):**
    *   **PromQL Query:** `sum(rate(django_http_requests_total_by_method_total[5m]))`
    *   **Visualization:** Time series graph.
    *   **Description:** Shows the total number of HTTP requests per second being handled by the application across all methods. `[5m]` represents a 5-minute sliding window for the rate calculation; adjust as needed.

*   **Request Rate by View/Endpoint:**
    *   **PromQL Query:** `sum(rate(django_http_requests_total_by_view_transport_method_total[5m])) by (view)`
    *   **Visualization:** Time series graph (use legend format like `{{view}}`) or a Bar chart for a snapshot.
    *   **Description:** Breaks down the request rate by individual Django view, helping identify the busiest parts of your application.

*   **Success Rate (e.g., percentage of non-5xx responses):**
    *   **PromQL Query:**
        ```promql
        (
          sum(rate(django_http_responses_total_by_status_view_method_total{status!~"5.."}[5m]))
        /
          sum(rate(django_http_responses_total_by_status_view_method_total[5m]))
        ) * 100
        ```
    *   **Visualization:** Time series graph or a Stat panel (set unit to "%").
    *   **Description:** Calculates the percentage of requests that did not result in a server-side error (HTTP 5xx).

### 2. Errors

Measures the rate and types of errors occurring.

*   **Overall Server Error Rate (5xx errors per second):**
    *   **PromQL Query:** `sum(rate(django_http_responses_total_by_status_view_method_total{status=~"5.."}[5m]))`
    *   **Visualization:** Time series graph.
    *   **Description:** Shows the rate of HTTP 5xx server-side errors. Useful for spotting widespread issues.

*   **Client Error Rate (4xx errors per second):**
    *   **PromQL Query:** `sum(rate(django_http_responses_total_by_status_view_method_total{status=~"4.."}[5m]))`
    *   **Visualization:** Time series graph.
    *   **Description:** Shows the rate of HTTP 4xx client-side errors (e.g., Not Found, Bad Request).

*   **Error Rate by View (5xx errors):**
    *   **PromQL Query:** `sum(rate(django_http_responses_total_by_status_view_method_total{status=~"5.."}[5m])) by (view)`
    *   **Visualization:** Time series graph (legend format `{{view}} - 5xx Errors`) or a Table.
    *   **Description:** Identifies which specific views are generating the most server errors.

*   **Specific Unhandled Exception Rate (e.g., `ValueError`):**
    *   **PromQL Query:** `sum(rate(django_http_exceptions_total_by_type_total{type="ValueError"}[5m]))`
    *   **Visualization:** Time series graph.
    *   **Description:** Tracks the rate of specific types of unhandled exceptions. You can create multiple queries on the same graph for different important exception types.

### 3. Latency

Measures the time taken to complete requests. Percentiles are often more useful than simple averages.

*   **Overall API Response Latency (e.g., 95th or 99th percentile):**
    *   **PromQL Query (95th percentile):**
        ```promql
        histogram_quantile(0.95, sum(rate(django_http_requests_latency_seconds_by_view_method_bucket[5m])) by (le, view, method))
        ```
    *   **Visualization:** Time series graph (set unit to "seconds").
    *   **Description:** Shows the 95th percentile response time. This means 95% of requests completed faster than this value. Helps identify slowdowns affecting a significant portion of users. You can also average across all views by removing `view, method` from the `by` clause: `histogram_quantile(0.95, sum(rate(django_http_requests_latency_seconds_by_view_method_bucket[5m])) by (le))`

*   **Latency by View (e.g., 95th percentile):**
    *   **PromQL Query (95th percentile for a specific view):**
        ```promql
        histogram_quantile(0.95, sum(rate(django_http_requests_latency_seconds_by_view_method_bucket{view="your_specific_view_name_here"}[5m])) by (le, method))
        ```
        (Replace `"your_specific_view_name_here"` with the actual view name from the `view` label)
    *   To see all views, group by view in the `sum by (...)` clause:
        ```promql
        histogram_quantile(0.95, sum(rate(django_http_requests_latency_seconds_by_view_method_bucket[5m])) by (le, view))
        ```
    *   **Visualization:** Time series graph (legend format `{{view}} P95 Latency`).
    *   **Description:** Tracks the 95th percentile latency for individual views.

*   **Database Query Latency (e.g., 95th percentile for the default database):**
    *   *(Assumes database monitoring is configured in `settings.py` by changing `DB_ENGINE` to `django_prometheus.db.backends.*`)*
    *   **PromQL Query (95th percentile):**
        ```promql
        histogram_quantile(0.95, sum(rate(django_db_query_latency_seconds_by_trans_vendor_alias_bucket{alias="default"}[5m])) by (le))
        ```
    *   **Visualization:** Time series graph (set unit to "seconds").
    *   **Description:** Monitors the performance of database queries.

### 4. Saturation

Measures how "full" your service is, indicating resource utilization. `django-prometheus` provides application-level metrics that can be strong indicators of saturation. For full system saturation (CPU, memory, disk), you'd typically use other exporters like `node_exporter`.

*   **High Average Latency as an Indicator:**
    *   Monitor the latency graphs created above. Sustained high latency or upward trends can signal saturation.
*   **High Error Rates as an Indicator:**
    *   Monitor the error rate graphs. A sudden spike in errors can occur when a system is overloaded.
*   **Database Connection/Cache Saturation (Indirect):**
    *   While `django-prometheus` doesn't directly expose connection pool counts, consistently high database or cache latencies can indicate those components are saturated.
    *   **Cache Hit Rate (example for default cache):**
        ```promql
        sum(rate(django_cache_hits_total{cache="default"}[5m]))
        /
        (sum(rate(django_cache_hits_total{cache="default"}[5m])) + sum(rate(django_cache_misses_total{cache="default"}[5m])))
        * 100
        ```
    *   **Visualization:** Time series graph or Stat panel (set unit to "%").
    *   **Description:** A low cache hit rate might mean the cache is undersized or inefficient, leading to more load on the database and potential saturation.

---

## Tips for Grafana Dashboards

*   **Start Simple:** Don't try to display too much information in a single graph or panel.
*   **Use Variables:** Create dashboard variables (e.g., a dropdown to select a specific `view`, `method`, or `status_code`). This makes your dashboards interactive and reusable. Find this under Dashboard Settings (cog icon) > Variables.
*   **Set Alerts:** Once you establish baseline performance, configure alerting rules in Grafana (Panel Edit > Alert tab) or in Prometheus/Alertmanager to notify you of critical issues (e.g., error rate exceeding X%, P99 latency > Y seconds).
*   **Organize with Rows:** Use "Rows" to group related panels on your dashboard (e.g., a row for "Traffic Metrics", another for "Error Metrics").
*   **Explore Metrics:** In Prometheus (`http://localhost:9090/graph`), type `django_` in the expression field to see all available metrics from your application. This exploration can inspire more useful visualizations.
*   **Consistent Time Ranges:** Ensure panels use consistent time ranges or the dashboard's global time range for meaningful correlation.
*   **Titles and Descriptions:** Clearly title your panels and add descriptions (under Panel options) to explain what the graph shows, especially for complex queries.

This guide provides a starting point. Tailor your dashboards to the specific needs and critical paths of your application. 