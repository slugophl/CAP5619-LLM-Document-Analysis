import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import re
import time

# Function to extract section text
def extract_text(html_content):
    # Parse the XML/HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    html_text = soup.get_text(separator=' ', strip=True)
    return html_text.replace(" ", " ").replace(" ", " ").replace(" ", " ").replace(" ", " ").replace(" ☐ ", " ")

ticker_cik_file_path = "s_p_500_master_ticker_name_cik.csv"

df_sp_500_cos = pd.read_csv(ticker_cik_file_path, dtype={'CIK': str}, sep=',')
print(df_sp_500_cos)

#df_100 = df.head(1) #df.sample(n=1)
#print(df_100)

# Standard headers for SEC API calls
headers = {
    "User-Agent": "student sa820782@ucf.edu",
    "Accept-Encoding": "gzip, deflate"
}

# Go through the last 20 SEC 8-K filings for as many companies as needed until I get 30 8-K filings that have new product/release information.
product_8k_filings = []
new_product_8k_filings = []
done = False
for index, row in df_sp_500_cos.iterrows():
    cik = row["CIK"]
    ticker = row["Symbol"]
    company_name = row["Security"]
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    print(f"submissions_url: {submissions_url}")

    # Make SEC submissions API call to get company submissions
    response = requests.get(submissions_url, headers=headers)

    # Check for success (status 200)
    if response.status_code != 200:
        raise Exception(f"Submissions API request failed for {cik} ({ticker}, {company_name}): {response.status_code}")

    # Get JSON response
    submission_data = response.json()

    # Get SEC filings for company
    filings = submission_data["filings"]["recent"]
    recent_filings = [
        {
            "accessionNumber": filings["accessionNumber"][i],
            "filingDate": filings["filingDate"][i],
            "form": filings["form"][i],
            "primaryDocument": filings["primaryDocument"][i]
        }
        for i in range(len(filings["form"]))
    ]

    # Get last 20 form 8-K filings
    form_8k_filings = [
        filing for filing in recent_filings
        if filing["form"] == "8-K" and filing["accessionNumber"]
    ][:20]

    # For each of last 20 filings, get the full text 8-K document
    filings_processed = []
    for filing in form_8k_filings:
        accession_number = filing["accessionNumber"].replace("-", "") # Document URL doesn't recognize dashes
        filing_date = filing["filingDate"]

        # Generate URL for primary document
        document_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/{filing['primaryDocument']}"
        print(f"Document URL: {document_url}")

        # Get 8-K document
        doc_response = requests.get(document_url, headers=headers)
        if doc_response.status_code == 200:
            text = extract_text(doc_response.text)

            # Remove extra whitespace
            text = " ".join(text.split())

            # Append to list that will hold last 20 8-K documents
            filings_processed.append({
                "accession_number": filing["accessionNumber"],
                "filing_date": filing_date,
                "text": text,
                "document_url": document_url,
                "ticker": ticker,
                "company_name": company_name
            })
        else:
            raise Exception(f"Failed to fetch document for {filing['accessionNumber']} ({ticker})")

    print(f"Number of filings processed: {len(filings_processed)}")

    # Loop through filings processed and make API call to Llama, stopping once I find an 8-K with a new product
    for fp in filings_processed:
        time.sleep(2)
        xai_url = "https://api.x.ai/v1/chat/completions"
        xai_api_key = "xai-D7vvsHo0E7ZLix3k5CXVzT4OjBWoFy244glj9Y6atrdFTC0T2YlkacR2FG6Asx9zXemXwmSTYlX79BTm"
        xai_headers = {
            "Authorization": f"Bearer {xai_api_key}",
            "Content-Type": "application/json"
        }

        text = fp["text"]
        content = (
            f"Analyze the following SEC Form 8-K filing for {fp["company_name"]} and only look for any mention of new products or service offerings. "
            "Ignore any mention of new Notes, debt securities, financial performance, financial results, business performance, stock performance, legal issues, stock repurchase, new roles for executives, or business strategy that are outside the context of new products or service offerings. "
            "Make sure that any mention of 'new' or 'purchase' or 'repurchase' or 'acquire' or 'acquired' or 'acquisition' is within the context of a new product or service offering. "
            "If you find mention of a new product or service offering, extract the company name, stock name, filing date, product or service name, and a brief description of the product or service in less than 180 words. Return this information in JSON format like: {\"company_name\": \"...\", \"stock_name\": \"...\", \"filing_date\": \"...\", \"product_service_name\": \"...\", \"product_service_description\": \"...\"}. "
            "Otherwise, if there is no mention of a new product, your response should be a JSON object with the format like: {\"company_name\": \"...\", \"stock_name\": \"...\", \"filing_date\": \"...\", \"product_service_name\": \"None\", \"product_service_description\": \"None\"}. "
            "Do not provide a description or highlights of what the report contains. I only want a JSON object.\n\n"
            f"Text: {text}"
        )
        # with open('prompt.txt', 'r') as prompt_file:
        #     content = prompt_file.read()
        #
        # content = content.replace("{company_name}", fp["company_name"]).replace("{text}", text)

        xai_data = {
            "model": "grok-beta",
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 512
        }

        try:
            response = requests.post(xai_url, headers=xai_headers, json=xai_data)
            print(f"xai response: {response.status_code}")

            response_text = json.loads(response.text)
            xai_response_text = response_text["choices"][0]["message"]["content"]
            print(xai_response_text)

            # Get JSON object in the xai_response
            pattern = r'```json(.*?)```'
            xai_response_json_match = re.search(pattern, xai_response_text, re.DOTALL)
            xai_response_json_str = ""
            if xai_response_json_match:
                xai_response_json_str = xai_response_json_match.group(1).strip()
            else:
                xai_response_json_str = xai_response_text

            try:
                xai_response_json = json.loads(xai_response_json_str)
                #xai_response_json["company_name_orig"] = fp["company_name"]
                #xai_response_json["ticker"] = fp["ticker"]
                xai_response_json["document_url"] = fp["document_url"]
                print(xai_response_json)

                if len(xai_response_json) == 0 or "No new product information found" in xai_response_json_str:
                    print(f"No new product information found in 8-K filing for {fp["document_url"]} ({fp["ticker"]}).")
                    product_8k_filings.append(xai_response_json)
                    new_product_8k_filings.append(xai_response_json)
                    with (open('xai_8k_filings.txt', 'a')) as file:
                        file.write(json.dumps(xai_response_json).replace("\n", "") + "\n")
                else:
                    print(f"New product information found for {fp["document_url"]} ({fp["ticker"]}).")
                    product_8k_filings.append(xai_response_json)
                    with (open('xai_8k_filings.txt', 'a')) as file:
                        file.write(json.dumps(xai_response_json).replace("\n", "") + "\n")
            except Exception as e:
                print(f"Exception converting JSON response from xAI to JSON object: {xai_response_json_str}.")
                print(f"Exception: {e}")
        except Exception as e:
            print(f"Exception making API call to xAI for {fp['accessionNumber']} ({fp["ticker"]}: {e}")

        # If length of new_product_8k_filings array is 30, break from the for loop
        if len(new_product_8k_filings) >= 30:
            done = True
            break

    if done:
        break

# Read from 8-K filings text file
json_list = []
with open('xai_8k_filings.txt', 'r', encoding='utf-8') as file:
    content = file.read().strip()
    if content.startswith('[') and content.endswith(']'):
        # Parse as a single JSON list
        json_list = json.loads(content)
    else:
        # Assume one JSON object per line
        file.seek(0)  # Reset file pointer to start
        for line in file:
            line = line.strip()
            if line:  # Skip empty lines
                json_obj = json.loads(line)
                json_list.append(json_obj)

# Write data to CSV file
df_output = pd.DataFrame(json_list)
df_output.to_csv("product_8k_filings_output.csv", index=False)