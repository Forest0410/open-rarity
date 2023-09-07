from os import environ
from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import pandas
from dateutil.parser import parse
import requests
import time
from open_rarity import (
    Collection,
    OpenRarityScorer,
    Token,
)
from open_rarity.rarity_ranker import RarityRanker
from open_rarity.resolver.opensea_api_helpers import (
    get_collection_from_opensea,
)
from open_rarity.scoring.handlers.information_content_scoring_handler import (
    InformationContentScoringHandler,
)
from open_rarity.scoring.handlers.arithmetic_mean_scoring_handler import (
    ArithmeticMeanScoringHandler,
)
from open_rarity.scoring.handlers.geometric_mean_scoring_handler import (
    GeometricMeanScoringHandler,
)
from open_rarity.scoring.handlers.harmonic_mean_scoring_handler import (
    HarmonicMeanScoringHandler,
)
from open_rarity.scoring.handlers.sum_scoring_handler import (
    SumScoringHandler,
)

# configuration
DEBUG = False

#-----------FLASK APP SET UP-----------------#
app = Flask(__name__)
# app.config['MONGO_DBNAME'] = environ.get('DB_NAME') or ''
# app.config["MONGO_URI"] = environ.get('DB_URI') or f'mongodb_uri_atlas'

CORS(app, resources={r'/*': {'origins': '*'}})  # enable CORS

def is_date(string, fuzzy=False):
    """
    Return whether the string can be interpreted as a date.

    :param string: str, string to check for date
    :param fuzzy: bool, ignore unknown tokens in string if True
    """
    try: 
        parse(string, fuzzy=fuzzy)
        return True

    except ValueError:
        return False
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
def getTokens(contractAddress):

    alchemy_key = "NxHb3Ed5rJbmcPy5pVAQv122_jhEFFtZ"
    # # GET METADATA for collection
    contract_url = "https://eth-mainnet.g.alchemy.com/nft/v2/{}/getContractMetadata?contractAddress={}".format(alchemy_key, contractAddress)
    headers = {"accept": "application/json"}
    response = requests.get(contract_url, headers=headers)
    contractInfo = json.loads(response.text)

    # Get all tokens from contract
    count = 0
    startToken=1
    tokens = []
    while 1:
        base_url = "https://eth-mainnet.g.alchemy.com/nft/v2/{}/getNFTsForCollection".format(alchemy_key)
        url = "{}?contractAddress={}&withMetadata=true&startToken={}".format(base_url, contractAddress, startToken)
        itemlist = []
        try:
            res = requests.get(url, headers = headers)
            itemlist = json.loads(res.text)
        except Exception as e:
            time.sleep(1.7)
            continue
        time.sleep(0.2)
        # print(todo_item)
        print('------', contractAddress, " ---------------", count)
        for item in itemlist["nfts"]:
            metadatas = {}
            if 'metadata' not in item or 'attributes' not in item['metadata']:
                continue
                # return jsonify({'data': [], 'error': "Can't load all nfts from collection now. Please try again later."}), []
            for attribute in item['metadata']['attributes']:
                key = "property"
                value = ""
                if 'trait_type' in attribute:
                    key = attribute['trait_type']
                if 'value' in attribute:
                    value = attribute['value']
                if is_date(str(value)) or is_number(str(value)):
                    continue
                metadatas[str(key)] = value
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
    score_handler = incoming['handler']
    contractInfo, tokens = getTokens(contractAddress)
    print("------- START --------------")
    # Calculate Score from collections.
    scorer = OpenRarityScorer(SumScoringHandler())
    collection = Collection(
        name=contractInfo['contractMetadata']['name'],
        tokens = tokens
    )
    token = collection.tokens[token_id]
    token_score = scorer.score_token(collection=collection, token=token)
    return jsonify({'data': token_score})

@app.route('/api/get_attrs', methods=['POST'])
def getAttributes():
    incoming = request.get_json()
    contractAddress = incoming['address']
    # contractAddress = "0x6562eccdf8B0A44BD4d68519Ee9550bf634111d9"
    contractInfo, tokens = getTokens(contractAddress)
    if len(tokens) == 0:
        return jsonify({'error': "Can't calculate rank now. Please try again later."})
    collection = Collection(
        name=contractInfo['contractMetadata']['name'],
        tokens = tokens
    )
    attribute_list = collection.extract_collection_attributes()
    attributes = {}
    for attr_key in attribute_list.keys():
        attributes[attr_key] = []
        for attr in attribute_list[attr_key]:
            attributes[attr_key].append({
                'attr_name': attr.attribute.value,
                'count': attr.total_tokens
            })
    print(contractAddress)
    return jsonify({'attributes': attributes})

def calculateRarity(handler, collection):
    rarityRanker = RarityRanker(handler)
    ranked_tokens = rarityRanker.rank_collection(collection=collection)
    rankings = []
    index = 1
    df = pandas.DataFrame(ranked_tokens)
    rankList = df.pivot_table(columns=['rank'], aggfunc='size').reset_index().rename_axis(None, axis=1).T.to_dict().values()
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
    return rankings

@app.route('/api/get_rarity', methods=['POST'])
def getRarity():
    incoming = request.get_json()
    contractAddress = incoming['contractAddress']
    print(contractAddress)
    # token_id = incoming['tokenID'] -1
    # handler_req = incoming['handler']
    # contractAddress = "0x6562eccdf8B0A44BD4d68519Ee9550bf634111d9"
    # token_id = 3
    contractInfo, tokens = getTokens(contractAddress)
    if len(tokens) == 0:
        return jsonify({'error': "Can't calculate rank now. Please try again later."})
    print("------- START --------------")
    # Calculate Score from collections.
    # scorer = OpenRarityScorer(HarmonicMeanScoringHandler())
    collection = Collection(
        name=contractInfo['contractMetadata']['name'],
        tokens = tokens
    )
    # token_scores = scorer.score_collection(collection=collection)
    # print(f"Token scores for collection: {token_scores}")
    # ranked_tokens = RarityRanker.set_rarity_ranks(token_scores)
    # print(ranked_tokens)
    data = {}
    inforRank = calculateRarity(InformationContentScoringHandler(), collection)
    data['inforRank'] = inforRank
    arithRank = calculateRarity(ArithmeticMeanScoringHandler(), collection)
    data['arithRank'] = arithRank
    geoRank = calculateRarity(GeometricMeanScoringHandler(), collection)
    data['geoRank'] = geoRank
    harmonicRank = calculateRarity(HarmonicMeanScoringHandler(), collection)
    data['harmonicRank'] = harmonicRank
    sumRank = calculateRarity(SumScoringHandler(), collection)
    data['sumRank'] = sumRank
    return jsonify(data)

@app.route('/api/get_rarity_from_opensea', methods=['POST'])
def getRarityfromOpensea():
    slug = 'mytoken-6fw24wpdur'
    # Create OpenRarity collection object from OpenSea API
    collection = get_collection_from_opensea(slug)
    print("collection")

    # Generate scores for a collection
    ranked_tokens = RarityRanker.rank_collection(collection=collection)
    print("Ranking")

    # Iterate over the ranked and sorted tokens
    for token_rarity in ranked_tokens:
        token_id = token_rarity.token.token_identifier.token_id
        rank = token_rarity.rank
        score = token_rarity.score
        print(f"\tToken {token_id} has rank {rank} score: {score}")
    return jsonify({'data': []})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=environ.get('PORT') or 8080, debug=DEBUG)
