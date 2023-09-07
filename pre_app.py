from concurrent.futures import thread
from operator import truediv
from os import environ
from urllib.request import urlopen
from flask import Flask, jsonify, request, g
from flask_pymongo import PyMongo
from flask_cors import CORS
import json
import pandas
import requests
from .open_rarity import (
    Collection,
    OpenRarityScorer,
    Token,
)
from .open_rarity.rarity_ranker import RarityRanker

# configuration
DEBUG = True

#-----------FLASK APP SET UP-----------------#
app = Flask(__name__)
# app.config['MONGO_DBNAME'] = environ.get('DB_NAME') or ''
# app.config["MONGO_URI"] = environ.get('DB_URI') or f'mongodb_uri_atlas'
app.config['MONGO_DBNAME'] = 'db_kpi_2021'
app.config["MONGO_URI"] = 'mongodb://localhost:27017/db_kpi_2021'
mongo = PyMongo(app)
CORS(app, resources={r'/*': {'origins': '*'}})  # enable CORS

def getTokens(contractAddress):

    alchemy_key = "_-kQiClQsdwzRsXfbOz2vGmolOl6Ftej"
    # # GET METADATA for collection
    contract_url = "https://eth-goerli.g.alchemy.com/nft/v2/{}/getContractMetadata?contractAddress={}".format(alchemy_key, contractAddress)
    headers = {"accept": "application/json"}
    response = requests.get(contract_url, headers=headers)
    contractInfo = json.loads(response.text)

    # Get all tokens from contract
    count = 0
    startToken=1
    tokens = []
    while 1:
        base_url = "https://eth-goerli.g.alchemy.com/nft/v2/{}/getNFTsForCollection".format(alchemy_key)
        url = "{}?contractAddress={}&withMetadata=true&startToken={}".format(base_url, contractAddress, startToken)
        res = requests.get(url, headers = headers)
        itemlist = json.loads(res.text)
        # print(todo_item)
        print("---------------", count)
        for item in itemlist["nfts"]:
            metadatas = {}
            if 'metadata' not in item or 'attributes' not in item['metadata']:
                return jsonify({'data': [], 'error': "Can't load all nfts from collection now. Please try again later."}), []
            for attribute in item['metadata']['attributes']:
                key = "property"
                value = ""
                if 'trait_type' in attribute:
                    key = attribute['trait_type']
                if 'value' in attribute:
                    value = attribute['value']
                metadatas[key] = value
            tokens.append(
                Token.from_erc721(
                    contract_address=item['contract']['address'],
                    token_id=int(item['id']['tokenId'], 16),
                    metadata_dict=metadatas,
                )
            )
        count +=1
        if "nextToken" in itemlist:
            startToken = itemlist["nextToken"]
            continue
        else :
            break
    return contractInfo, tokens

@app.route('/api/get_score', methods=['POST'])
def getscore_token():
    incoming = request.get_json()
    contractAddress = incoming['contractAddress']
    token_id = incoming['tokenID']
    contractInfo, tokens = getTokens(contractAddress)
    print("------- START --------------")
    # Calculate Score from collections.
    scorer = OpenRarityScorer()
    collection = Collection(
        name=contractInfo['contractMetadata']['name'],
        tokens = tokens
    )
    token = collection.tokens[token_id]
    token_score = scorer.score_token(collection=collection, token=token)
    return jsonify({'data': token_score})

@app.route('/api/get_rarity', methods=['POST'])
def getRarity():
    incoming = request.get_json()
    contractAddress = incoming['contractAddress']
    token_id = incoming['tokenID'] -1
    # contractAddress = "0x6562eccdf8B0A44BD4d68519Ee9550bf634111d9"
    # token_id = 3
    contractInfo, tokens = getTokens(contractAddress)
    if len(tokens) == 0:
        return jsonify({'error': "Can't calculate rank now. Please try again later."})
    print("------- START --------------")
    # Calculate Score from collections.
    scorer = OpenRarityScorer()
    collection = Collection(
        name=contractInfo['contractMetadata']['name'],
        tokens = tokens
    )
    # token_scores = scorer.score_collection(collection=collection)
    # print(f"Token scores for collection: {token_scores}")
    # print(token_score)
    ranked_tokens = RarityRanker.rank_collection(collection=collection)
    rankings = []
    index = 1
    df = pandas.DataFrame(ranked_tokens)
    rankList = df.pivot_table(columns=['rank'], aggfunc='size').reset_index().rename_axis(None, axis=1).T.to_dict().values()
    print(rankList)
    for ranked_token in ranked_tokens:
        rankings.append({
            'token_id': ranked_token.token.token_identifier.token_id,
            'rank': ranked_token.rank,
            'score': ranked_token.score,
            'index': index,
            'same': next(item for item in rankList if item["rank"] == ranked_token.rank)[0],
            'total': len(ranked_tokens)
        })
        index += 1
    return jsonify({'data': {
        'token_id': ranked_tokens[token_id].token.token_identifier.token_id,
        'rank': ranked_tokens[token_id].rank,
        'score': ranked_tokens[token_id].score,
        'same': next(item for item in rankList if item["rank"] == ranked_tokens[token_id].rank)[0],
        'total': len(ranked_tokens)
        }})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=environ.get('PORT') or 8080, thread = True)
