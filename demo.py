"""
demo.py
Apr 2025 PJW

Demonstrate several web scraping techniques. Stores output in a SQLite 
database with two tables: one for races and one for individual results.
The tables are created on the fly by calls to pd.to_sql().
"""

import pandas as pd
import requests
from io import StringIO
from bs4 import BeautifulSoup
import sqlite3
import json
import matplotlib.pyplot as plt

#
#  Set up the output name and key features for scraping results from
#  several years of the Syracuse Mountain Goat race
#

dbname = 'goat.db'

base_url = "https://www.leonetiming.com/results/index.php"

#  
#  Server's ID numbers of races, obtained from looking at URLs offered
#  by the server.
#

races = {
    2016: 2620,
    2017: 3014,
    2018: 4082,
    2019: 4414,
    2021: 5051,
    2022: 5104,
    2023: 5272,
    }

#
#  Can force reloading by adding years to this list
#

force_reload = [] 

#
#  Connect to the database
#
    
con = sqlite3.connect(dbname)

#
#  See if there's already a table for races. If so, see what years
#  have already been collected and shorten the races dictionary 
#  accordingly.
#

tables = pd.read_sql("SELECT * FROM sqlite_schema;",con)
print(tables)

has_races = 'races' in list( tables['name'] )

if has_races:
    
    print('\nTable for races found\n')
    
    cur = con.execute("SELECT DISTINCT year FROM races;")
    rows = cur.fetchall()
    
    years_done = [r[0] for r in rows]

    for year in years_done:
        if year in races:
            
            #
            #  Is this in the force_reload list? If so, erase current data.
            #
            
            if year in force_reload:
                with con:
                    cur = con.execute(f"DELETE FROM races WHERE year={year};")
                    n_races = cur.rowcount
                    cur = con.execute(f"DELETE FROM results WHERE year={year};")
                    n_results = cur.rowcount
                    print(f"Removed {n_races} race with {n_results} entries in {year}")
            
            #
            #  Found but not in force_reload: remove from to-do list
            #
            
            else:
                print('Data already collected for',year)
                del races[year]

#
#  Say what we have to do
#

print('\nRaces remaining to scrape:')
print(json.dumps(races,indent=4))

#
#  Set up a function for getting one page of results from a given race
#

def get_page(race:int, pagenum: int) -> tuple:

    #
    #  Get the page
    #
    
    payload = {"id":race, 'page':pagenum}
    response = requests.get(base_url,payload)
    assert response.status_code == 200
    
    #
    #  Parse it to create a BeautifulSoup objeect
    #
    
    soup = BeautifulSoup(response.text,'html.parser')
    
    #
    #  Get the page title, trim it to the race name, and print it
    #
    
    title = soup.find('title').text
    title = title.split('|')[0].strip()
    print(title)
    
    #
    #  Figure out the maximum number of pages listed in the block. 
    #
    #  Start by finding the <DIV> that manages paging. It has class="paging"
    #
    
    paging = soup.find('div',{'class':'paging'})
    
    #
    #  Find the <p> tag within it that has class="pages"
    #
    
    pages = paging.find('p',{'class':'pages'})
    
    #
    #  Get a list of all the <a> tags in the list of pages. These are 
    #  buttons a user could click.
    #
    
    alist = pages.findAll('a')
    
    #
    #  Make a list of the text of each <a> tag, which is the part between the 
    #  <a> and </a> tags. These will be available page numbers.
    #
    
    pagelist = [int(a.text) for a in alist]
    
    #
    #  Find the largest one
    #
    
    pagemax = max(pagelist)
    
    #
    #  Now feed the whole web page into the Pandas .read_html() function. 
    #  The StringIO function allows Pandas to read an in-memory string
    #  in a context where it would usually expect to see a file name
    #  or open file handle.
    #
    #  The .read_html() function returns a list of all the tables it 
    #  can find in the document.
    #
    
    tables = pd.read_html(StringIO(response.text))

    #
    #  In this case, there should be exactly one table. Check that and then 
    #  extract it from the list
    #
    
    assert len(tables) == 1
    results = tables[0]
    
    #
    #  Return the table of results, the maximum page number found, and the title
    #
    
    return (results,pagemax,title)

#
#  Define a function to retrieve a whole race even though it might be spread
#  across several pages
#

def get_race(race:int) -> pd.DataFrame:

    #
    #  Set the initial page number and provide a starting guess about
    #  the maximum number of pages.
    #
    
    numpage = 1
    pagemax = 1
    
    #
    #  Walk through the pages, updating the maximum page each time since
    #  some web pages only provide a partial menu of available pages (e.g., 
    #  the next 5).
    #
    #  This is particularly common when the full list is very long: web 
    #  designers don't want to create dozens of different year buttons.
    #
    #  For each page, add the dataframe from get_page() to a list and 
    #  increment the page counter.
    #
    
    results_list = []
    while numpage <= pagemax:
        print('\nGetting page',numpage,'of',pagemax,flush=True)    
        (results,pagemax,title) = get_page(race,numpage)
        results_list.append(results)
        numpage += 1

    #
    #  Done collecting pages: concatenate the dataframes
    #
    
    results = pd.concat(results_list)
    
    #
    #  Return the results, and the page title as well
    #
    
    return (results,title)

#
#  Now do the actual work.
#

cols = {}
for year,race in races.items():

    #
    #  Get the results for this year
    #
    
    print('\nResults for',year)
    (results,title) = get_race(race)
    
    #
    #  Add a field indicating the year
    #
    
    results['year'] = year
    
    cols[year] = results.columns

    # 
    #  Build a tiny dataframe with information about the race itself
    #  Will be stored in a "races" table.
    #
    
    raceinfo = pd.DataFrame(
        columns=["year","title","id","entries"],
        data=[[year,title,race,len(results)]])

    #
    #  Add the results to table "results" and make an entry in table "races"
    #  to indicate that this year's results have been collected. 
    #
    #  In both cases, set index=False to avoid retaining it in the
    #  databank.
    #
    #  Note that .to_sql() automatically commits after each call, so we're
    #  not guaranteed that both tables will be updated (although a crash
    #  during the second call is very unliely)
    #
    
    n = results.to_sql('results',con,if_exists='append',index=False)
    print(f'Updated {n} results',flush=True)

    raceinfo.to_sql('races',con,if_exists='append',index=False)
    print('Updated races',flush=True)

#
#  Done with the retrievals
#
    
#%%
#
#  Look at what we found
#

races = pd.read_sql("""
    SELECT RA.year, title, sex, COUNT(*) AS entries FROM races AS RA
        JOIN results AS RE ON RA.year = RE.year
            GROUP BY RE.year,sex;
    """, con)

#
#  Make a nice printout
#

races = races.pivot(index=['year','title'],columns='Sex',values='entries')

print('Race information:')
print(races)

#
#  Now draw a bar graph. The index will be the Y axis, so trim it down to 
#  just the year.
#

races.index = races.index.droplevel('title')

#
#  Draw a stacked bar plot
#

fig,ax = plt.subplots()
fig.suptitle('Syracuse Mountain Goat Entries')
races.plot.bar(stacked=True,ax=ax)
ax.set_ylabel('Entries')
ax.set_xlabel('')
fig.tight_layout()
fig.savefig('goat.png')

