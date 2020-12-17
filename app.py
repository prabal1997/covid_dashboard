import streamlit as st
import os
import sys
import pandas as pd
import numpy as np
import altair as alt
from vega_datasets import data
import iso3166
import argparse
from newsapi import NewsApiClient

CONTINENTS = ("World", "Asia", "North America", "South America", "Africa", "Europe", "Oceania",)
CONTINENTS_EMOJI = ("🗺️", "🌏", "🌎", "🌎", "🌍", "🌍", "🌏",)

CONTINENTS_ROTATION = [
                        {"type": "mercator"
                        }, 
                        {"type": "mercator",
                        },
                        {"type": "mercator"
                        },
                        {"type": "mercator"
                        },
                        {"type": "mercator"
                        },
                        {"type": "mercator",
                        "scale": 275,
                        "center": [20, 60]#,
                        },
                        {"type": "mercator",
                        "scale": 400,
                        "center": [150, -30]#,
                        }]
CONTINENTS_ROTATION = {key:params for key, params in zip(CONTINENTS, CONTINENTS_ROTATION)}

# aggregate data to calculate required statistics across countries at present moment
def calculate_linechart_stats(input_frame):
    def aggregate_rates_across_countries(input_rate, input_country_population):
        return ((input_rate * input_country_population).sum())/(input_country_population.sum())
        
    return pd.Series({"population": input_frame["population"].sum(),
                        "new_cases": input_frame["new_cases"].sum(),
                        "new_cases_smoothed": input_frame["new_cases_smoothed"].sum(),
                        "new_deaths": input_frame["new_deaths"].sum(),
                        "new_deaths_smoothed": input_frame["new_deaths_smoothed"].sum(),
                        "new_cases_smoothed_per_million" : aggregate_rates_across_countries(input_frame["new_cases_smoothed_per_million"], input_frame["population"]), 
                        "new_deaths_smoothed_per_million" : aggregate_rates_across_countries(input_frame["new_deaths_smoothed_per_million"], input_frame["population"]),
                        "positive_rate" : aggregate_rates_across_countries(input_frame["positive_rate"], input_frame["population"])})

def calculate_map_stats(input_frame):
    return pd.Series({"total_cases_smoothed": np.round(input_frame["new_cases_smoothed"].sum()),
                        "total_deaths_smoothed" : np.round(input_frame["new_deaths_smoothed"].sum()),
                        "total_cases_smoothed_per_million" : input_frame["new_cases_smoothed_per_million"].sum(), 
                        "total_deaths_smoothed_per_million" : input_frame["new_deaths_smoothed_per_million"].sum()})

@st.cache
def fetch_covid_data(date, DATA_URL="https://covid.ourworldindata.org/data/owid-covid-data.csv"):

    # load COVID data by country, continent
    covid_data = pd.read_csv(DATA_URL)
    covid_data["date"] = pd.to_datetime(covid_data["date"])
    
    # remove the 'World' location so as to not double-calculate any number
    covid_data = covid_data.query("location != 'World'")

    map_covid_data = covid_data.groupby(["iso_code", "continent", "location"]).apply(calculate_map_stats).reset_index()

    alpha3_to_id = dict()
    for country_alpha3 in iso3166.countries_by_alpha3:
        alpha3_to_id[country_alpha3] = int(iso3166.countries_by_alpha3[country_alpha3].numeric)
    map_covid_data['id'] = map_covid_data['iso_code']
    map_covid_data['id'] = map_covid_data['id'].replace(alpha3_to_id)
    
    # aggregate data to calculate required statistics since start of pandemic
    
    linechart_covid_data = covid_data.groupby(["continent", "date"]).apply(calculate_linechart_stats).reset_index()

    return {"map": map_covid_data, "linechart": linechart_covid_data}


def cache_covid_news(covid_data_map_full,
                     NEWS_API_KEY,                     
                     start_date=(pd.Timestamp.today() - pd.Timedelta("7d")).strftime("%Y-%m-%d")):
    
    # fetch covid news relevant to specific countries
    def fetch_covid_news(continent="", country_list=[]):
        # Init
        newsapi = NewsApiClient(api_key=NEWS_API_KEY)
        if (len(continent)):
            country_list = list(country_list) + [continent]
        country_list = list(country.lower() for country in country_list)

        # fetch news within past week
        SEARCH_KEYWORDS = ("corona", "covid", "pandemic", "coronavirus", "covid19", "covid-19")
        search_keywords_query = "({})".format(" OR ".join("\"{}\"".format(element) for element in SEARCH_KEYWORDS))
        search_country_query =  "({})".format(" OR ".join("\"{}\"".format(element) for element in country_list))
        if (len(country_list)):
            query = "{0} AND {1}".format(search_keywords_query, search_country_query)
            sort_method = 'relevancy'
        else:
            query = search_keywords_query
            sort_method = 'relevancy'

        try:
            @st.cache
            def call_news_api(query, start_date, sort_method):
                # return {'status': "ok",
                #         'totalResults': 2,
                #         'articles': [{'title': "COVID coronavirus asia north america canada is in the title!",
                #                       'description': "Some news description",
                #                       'content': "A looooong news article",
                #                       'url': "https://www.google.com",
                #                       "author": "My Name",
                #                       "source": {"id": "news_company",
                #                                  "name": "News Company"}}
                #                      ]*2}

                return newsapi.get_everything(q=query,
                                              from_param=start_date,
                                              sort_by=sort_method,
                                              language='en')
            api_response = call_news_api(query, start_date, sort_method)

            if ((api_response['status'] == 'ok') and (api_response['totalResults'])):
                news_list = api_response['articles']
                
                def keywords_in_news_article(news_article_input, search_keywords_list):
                    combined_text = (str(news_article_input['title']) + str(news_article_input['description']) + str(news_article_input['content'])).lower()
                    contains_some_keywords = any((search_keyword in combined_text) for search_keyword in search_keywords_list)     
                    
                    return contains_some_keywords

                news_list = list(news_article for news_article in news_list if (keywords_in_news_article(news_article, SEARCH_KEYWORDS)))
                if (len(country_list)):
                    news_list = list(news_article for news_article in news_list if (keywords_in_news_article(news_article, country_list)))                
                else:
                    pass
                    # st.write(news_list)

                return news_list
            
        except Exception as e:
            print(e)
        return []
    
    # fetch covid news for each continent, and for the world
    covid_continet_countries_dict = covid_data_map_full[["continent", "location"]].drop_duplicates().groupby('continent').apply(lambda x: tuple(x['location'])).to_dict()
    covid_continent_news_dict = dict()
    for continent in covid_continet_countries_dict:
        covid_continent_news_dict[continent] = fetch_covid_news(continent=continent,
                                                                country_list=covid_continet_countries_dict[continent])
    covid_continent_news_dict["World"] = fetch_covid_news()
        
    return covid_continent_news_dict

# parse command line arguments to receive information about NEWS API key
parser = argparse.ArgumentParser(description='This webapp serves as a simple COVID19 dashboard')

parser.add_argument('--news_api_key', action="store", default="",
                    help="Enter the key for using the News API, or set the NEWS_API_KEY environment variable to hold the API key")

try:
    args = parser.parse_args()
except SystemExit as e:
    # This exception will be raised if --help or invalid command line arguments
    # are used. Currently streamlit prevents the program from exiting normally
    # so we have to do a hard exit.
    os._exit(e.code)
NEWS_API_KEY = args.news_api_key

# try checking environment variables if the key is unavailable in command-line arguments
NEWS_API_KEY = str(os.environ.get("NEWS_API_KEY")) if ((NEWS_API_KEY is None) or (NEWS_API_KEY=="")) else NEWS_API_KEY

# add a title
st.set_page_config(page_title="COVID19 Dashboard", page_icon="👾")
st.title("🦠 Coronavirus Dashboard")

# select a location
selectbox_options = list("{0} {1}".format(name, emoji) for name, emoji in zip(CONTINENTS, CONTINENTS_EMOJI))
def selectbox_option_to_location(input_selectbox_option):
    return input_selectbox_option[:input_selectbox_option.rfind(' ')]

st.header("📈 Pandemic Trend")
location_selectbox = st.selectbox("Please Choose a Region", selectbox_options)

# fetch data relevant to the location, sort by date
date_today = (pd.Timestamp.today()).strftime("%Y-%m-%d") 
date_weekago = (pd.Timestamp.today() - pd.Timedelta("7d")).strftime("%Y-%m-%d")
covid_data = fetch_covid_data(date_today)
location = selectbox_option_to_location(location_selectbox)

IS_WORLD = (location == "World")
covid_data_map_full = covid_data["map"] 
if not(IS_WORLD):
    covid_data_query = ("continent == '{0}'".format(location))
    covid_data_linechart = covid_data["linechart"].query(covid_data_query)

    covid_data_map = covid_data_map_full.query(covid_data_query)
else:
    covid_data_linechart = covid_data["linechart"].copy(deep=True)
    covid_data_linechart = covid_data_linechart.groupby("date").apply(calculate_linechart_stats).reset_index()

    covid_data_map = covid_data_map_full.copy(deep=True)

    # remove incorrect data-points that do not include every nation
    MIN_POPULATION_THRESHOLD = 7.5 * (10**9)
    covid_data_linechart = covid_data_linechart.query("population >= {0}".format(MIN_POPULATION_THRESHOLD))

covid_data_linechart = covid_data_linechart.sort_values(by="date", ascending=True)

SKIP_SAMPLES = 0
if (SKIP_SAMPLES > 0):
    covid_data_linechart = covid_data_linechart.iloc[:-SKIP_SAMPLES]

# calculate the range and the domain - only include output values less than 99th percentile
DATE_DOMAIN = [pd.to_datetime("2020-03-01"), covid_data_linechart['date'].iloc[-1] + pd.Timedelta("14d")]

PERCENTILE_TOLERANCE = 99
MARGIN = 0.1
OUTPUT_RANGE = [0, np.percentile(covid_data_linechart['new_cases'], PERCENTILE_TOLERANCE) * (1 + MARGIN)]

# define the x, y axis of the plot
x_axis = alt.X('date:T',
            axis=alt.Axis(title="Date"),
            scale=alt.Scale(zero=False, domain=DATE_DOMAIN)) 
y_axis = alt.Y('new_cases:Q',
            axis=alt.Axis(title='New Cases'),
            scale=alt.Scale(zero=False, type='linear', domain=OUTPUT_RANGE))
y_smooth_axis = alt.Y('new_cases_smoothed:Q',
            axis=alt.Axis(title='New Cases'),
            scale=alt.Scale(zero=False, type='linear', domain=OUTPUT_RANGE))

# define the template for what the tooltip(s) will look like when a user hovers on the scatter points on the graph
tooltip = [alt.Tooltip("new_cases:Q", title="New Cases", format=",r"),
           alt.Tooltip("new_deaths:Q", title="New Deaths", format=",r"),
           alt.Tooltip("positive_rate:Q", title="Positivity Rate", format = ".3%"),
           alt.Tooltip("date:T", title="Date")]

# make a scatter plot
scatter_plot = alt.Chart(covid_data_linechart).mark_circle().encode(
    x=x_axis,
    y=y_axis,
    size=alt.Size('new_deaths_smoothed', title="New Deaths", legend=alt.Legend(orient="bottom")),
    color=alt.Color('positive_rate', title="Positivity Rate", legend=alt.Legend(orient="top", format=".1%")),
    tooltip = tooltip
).properties(height=500, title="New Cases, Deaths, and Positivity Rates").interactive()

# make a line plot
line = alt.Chart(covid_data_linechart).mark_line(
    color='red',
    opacity=0.625,
    size=3
).encode(
    x=x_axis,
    y=y_smooth_axis
).interactive()

# combine the scatter, line plot and show on the screen
st.altair_chart((scatter_plot + line).configure_view(strokeWidth=2), use_container_width=True)

# make a map in Altair
st.header("🌡 Pandemic Heatmap")

TOTAL_CASES_LABEL = "Total Cases Per Million"
TOTAL_DEATHS_LABEL = "Total Deaths Per Million"
chosen_metric = st.selectbox("Please Choose a Metric", (TOTAL_CASES_LABEL, TOTAL_DEATHS_LABEL,))

if (chosen_metric == TOTAL_CASES_LABEL):
    metric_column_name = "total_cases_smoothed_per_million"
    scale = "linear"    
else:
    metric_column_name = "total_deaths_smoothed_per_million"    
    scale = "linear"

tooltip = [alt.Tooltip("location:N", title="Country"),
           alt.Tooltip("total_cases_smoothed:Q", title="Total Cases", format=",r"),
           alt.Tooltip("total_deaths_smoothed:Q", title="Total Deaths", format=",r"),
           alt.Tooltip("total_cases_smoothed_per_million:Q", title="Total Cases Per Million", format=",r"), 
           alt.Tooltip("total_deaths_smoothed_per_million:Q", title="Total Deaths Per Million", format=",r")]

countries = alt.topo_feature(data.world_110m.url, 'countries')
foreground = alt.Chart(countries).mark_geoshape(stroke="white", strokeWidth=0.30
).encode(color=alt.Color('{}:Q'.format(metric_column_name), 
                        scale=alt.Scale(scheme="reds", type="linear"), title=chosen_metric, legend=alt.Legend(orient="top")),
                        tooltip=tooltip,
).transform_lookup(
    lookup='id',
    from_=alt.LookupData(covid_data_map, 'id', ['total_cases_smoothed', 'total_deaths_smoothed', 'total_cases_smoothed_per_million', 'total_deaths_smoothed_per_million', 'continent', 'location'])
)

final_map = (
    foreground
    .configure_view(strokeWidth=0)
    .properties(height=500)
    .project(**CONTINENTS_ROTATION[location])
)
st.altair_chart(final_map, use_container_width=True)

# get news about COVID
def show_news(title, url, author, news_agency, urlToImage):
    st.subheader("[{title}]({url})".format_map({"title": title,
                                                "url": url}))
    if (author):
        st.write("by **{author}** in **{news_agency}**".format_map({"author": author,
                                                                    "news_agency": news_agency}))
    else:
        st.write("by **{news_agency}**".format_map({"news_agency": news_agency}))

covid_news_cache = cache_covid_news(covid_data_map_full, NEWS_API_KEY)
news_articles = covid_news_cache[location]

if (len(news_articles)):
    # show title, source name, and URL
    st.header("📰 Regional News")
    SHOWN_TITLES = set()

    # show articles with unique headlines
    MAX_ARTICLE_COUNT = 5
    for news_article in news_articles[:MAX_ARTICLE_COUNT]:
        title = news_article['title']
        url = news_article['url']
        author = news_article['author']
        news_agency = news_article['source']['name']
        urlToImage = news_article['urlToImage']

        if (title not in SHOWN_TITLES):
            show_news(title, url, author, news_agency, urlToImage)
            SHOWN_TITLES.add(title) 
