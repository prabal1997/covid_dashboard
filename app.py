import streamlit as st
import urllib
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import altair as alt
from vega_datasets import data
import altair as alt
from vega_datasets import data
import iso3166

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
def fetch_covid_data(DATA_URL="https://covid.ourworldindata.org/data/owid-covid-data.csv"):

    # load COVID data by country, continent
    covid_data = pd.read_csv(DATA_URL)
    covid_data["date"] = pd.to_datetime(covid_data["date"])


    map_covid_data = covid_data.groupby(["iso_code", "continent", "location"]).apply(calculate_map_stats).reset_index()

    alpha3_to_id = dict()
    for country_alpha3 in iso3166.countries_by_alpha3:
        alpha3_to_id[country_alpha3] = int(iso3166.countries_by_alpha3[country_alpha3].numeric)
    map_covid_data['id'] = map_covid_data['iso_code']
    map_covid_data['id'] = map_covid_data['id'].replace(alpha3_to_id)
    
    # aggregate data to calculate required statistics since start of pandemic
    
    linechart_covid_data = covid_data.groupby(["continent", "date"]).apply(calculate_linechart_stats).reset_index()

    return {"map": map_covid_data, "linechart": linechart_covid_data}

# add a title
st.title("🦠 Coronavirus Dashboard")

# select a location
selectbox_options = list("{0} {1}".format(name, emoji) for name, emoji in zip(CONTINENTS, CONTINENTS_EMOJI))
def selectbox_option_to_location(input_selectbox_option):
    return input_selectbox_option[:input_selectbox_option.rfind(' ')]

st.header("Coronavirus Daily Status")
location_selectbox = st.selectbox("Please Choose a Region", selectbox_options)

# fetch data relevant to the location, sort by date
covid_data = fetch_covid_data()
location = selectbox_option_to_location(location_selectbox)

IS_WORLD = (location == "World")
if not(IS_WORLD):
    covid_data_query = ("continent == '{0}'".format(location))
    covid_data_linechart = covid_data["linechart"].query(covid_data_query)

    covid_data_map = covid_data["map"].query(covid_data_query)
else:
    covid_data_linechart = covid_data["linechart"].copy(deep=True)
    covid_data_linechart = covid_data_linechart.groupby("date").apply(calculate_linechart_stats).reset_index()

    covid_data_map = covid_data["map"].copy(deep=True)

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
           alt.Tooltip("positive_rate:Q", title="Positivity Rate", format = ".3%")]

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
)

# combine the scatter, line plot and show on the screen
st.altair_chart((scatter_plot + line).configure_view(strokeWidth=2), use_container_width=True)

# make a map in Altair
tooltip = [alt.Tooltip("location:N", title="Country"),
           alt.Tooltip("total_cases_smoothed:Q", title="Total Cases", format=",r"),
           alt.Tooltip("total_deaths_smoothed:Q", title="Total Deaths", format=",r"),
           alt.Tooltip("total_cases_smoothed_per_million:Q", title="Total Cases Per Million", format=",r"), 
           alt.Tooltip("total_deaths_smoothed_per_million:Q", title="Total Deaths Per Million", format=",r")]

countries = alt.topo_feature(data.world_110m.url, 'countries')
foreground = alt.Chart(countries).mark_geoshape(stroke="white", strokeWidth=0.30
).encode(color=alt.Color('total_cases_smoothed_per_million:Q', 
                        scale=alt.Scale(scheme="turbo", type="log"), title="Total Cases Per Million", legend=alt.Legend(orient="top")),
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