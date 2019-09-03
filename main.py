import sys, os, json, shutil, time, traceback

from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

import pandas as pd
from sklearn.linear_model import SGDClassifier, Perceptron, PassiveAggressiveClassifier
import joblib
import numpy as np
import eli5

import nltk
from gensim.models.keyedvectors import KeyedVectors
ar_model = KeyedVectors.load_word2vec_format('wiki.ar.vec')

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = './uploads'
ALLOWED_EXTENSIONS = {'txt', 'csv'}

# inputs
training_data = 'data/titanic.csv'
include = ['Age', 'Sex', 'Embarked', 'Survived']
dependent_variable = include[-1]

model_directory = 'model'
model_file_name = '%s/model.pkl' % model_directory
model_columns_file_name = '%s/model_columns.pkl' % model_directory

# These will be populated at training time
model_columns = None
clf = None


@app.route('/predict', methods=['POST'])
def predict():
    if clf:
        try:
            json_ = request.json
            query = pd.get_dummies(pd.DataFrame(json_))

            # https://github.com/amirziai/sklearnflask/issues/3
            # Thanks to @lorenzori
            query = query.reindex(columns=model_columns, fill_value=0)
            prediction = clf.predict(query)
            explainers = []
            for index, row in query.iterrows():
                op_exp = { 'pos': [], 'neg': [] }
                explanation = eli5.explain_prediction(clf, row).targets[0].feature_weights
                for feature in explanation.pos:
                    op_exp['pos'].append([feature.feature, feature.weight])
                for feature in explanation.neg:
                    op_exp['neg'].append([feature.feature, feature.weight])
                explainers.append(op_exp)

            # Converting to int from int64
            return jsonify({
                "predictions": list(map(int, prediction)),
                "explanations": explainers
            })

        except Exception as e:

            return jsonify({'error': e.message, 'trace': traceback.format_exc()})
    else:
        print('train first')
        return 'no model here'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_file(request):
    if 'file' not in request.files:
        raise Exception('no file included in POST')
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    else:
        raise Exception('need CSV file for upload')

def process_csv(filename, vectorize_text=False):
    df = pd.read_csv(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    categoricals = []  # going to one-hot encode categorical variables

    if vectorize_text:
        # first column is text
        # last column is dependent variable for classifier
        final_rows = []
        cols=[]
        for index, row in df.iterrows():
            words = tokenize(row[0])
            sentence_vecs = []
            for w in range(0, len(words)):
                word = words[w]
                word_vec = ar_model[word]
                for v in range(0, len(word_vec)):
                    if w == 0:
                        sentence_vecs.append(0)
                        sentence_vecs.append([])
                        sentence_vecs.append([])
                        cols += ['avg_' + str(v), 'min_' + str(v), 'max_' + str(v)]
                    sentence_vecs[v * 3] += word_vec[v]
                    sentence_vecs[v * 3 + 1].append(word_vec[v])
                    sentence_vecs[v * 3 + 2].append(word_vec[v])
            for v in range(0, len(sentence_vecs) / 3):
                sentence_vecs[v * 3] /= float(len(words))
                sentence_vecs[v * 3 + 1] = min(sentence_vecs[v * 3 + 1])
                sentence_vecs[v * 3 + 2] = max(sentence_vecs[v * 3 + 2])
            sentence_vecs += row[1:]
            cols += df.columns[1:]
            final_rows.append(sentence_vecs)
        df_ = pd.DataFrame(final_rows, columns=cols)
    else:
        # include array is columns of variables used in decision
        # last column is dependent variable for classifier
        df_ = df[include]

        for col, col_type in df_.dtypes.items():
            if col_type == 'O':
                categoricals.append(col)
            else:
                df_[col].fillna(0, inplace=True)  # fill NA's with 0 for ints/floats, too generic

        # get_dummies effectively creates one-hot encoded variables
        df_ohe = pd.get_dummies(df_, columns=categoricals, dummy_na=True)
    x = df_ohe[df_ohe.columns.difference([dependent_variable])]
    y = df_ohe[dependent_variable]
    return (x, y)

def fitme(x, y):
    global clf
    clf = Perceptron()
    clf.partial_fit(x, y, classes=np.unique(y))
    joblib.dump(clf, model_file_name)
    return clf

@app.route('/train/create', methods=['POST'])
def create_train():
    try:
        filename = validate_file(request)
    except Exception as e:
        print(e)
        return e.message

    (x, y) = process_csv(filename)

    # capture a list of columns that will be used for prediction
    global model_columns
    model_columns = list(x.columns)
    joblib.dump(model_columns, model_columns_file_name)

    start = time.time()
    fitme(x, y)

    message1 = 'Trained in %.5f seconds' % (time.time() - start)
    message2 = 'Model training score: %s' % clf.score(x, y)
    return_message = 'Success. \n{0}. \n{1}.'.format(message1, message2)
    return return_message

@app.route('/train_text/create', methods=['POST'])
def create_text():
    try:
        filename = validate_file(request)
    except Exception as e:
        print(e)
        return e.message

    (x, y) = process_csv(filename, vectorize_text=True)

    # capture a list of columns that will be used for prediction
    global model_columns
    model_columns = list(x.columns)
    joblib.dump(model_columns, model_columns_file_name)

    start = time.time()
    fitme(x, y)

    message1 = 'Trained in %.5f seconds' % (time.time() - start)
    message2 = 'Model training score: %s' % clf.score(x, y)
    return_message = 'Success. \n{0}. \n{1}.'.format(message1, message2)
    return return_message

@app.route('/train/insert', methods=['POST'])
def insert_train():
    if clf:
        try:
            filename = validate_file(request)
        except Exception as e:
            print(e)
            return e.message

        (x, y) = process_csv(filename)
        fitme(x, y)
        return 'Success\nModel training score: %s' % clf.score(x, y)
    else:
        print('train first')
        return 'no model here'

@app.route('/train_text/insert', methods=['POST'])
def insert_text():
    if clf:
        try:
            filename = validate_file(request)
        except Exception as e:
            print(e)
            return e.message

        (x, y) = process_csv(filename, vectorize_text=True)
        fitme(x, y)
        return 'Success\nModel training score: %s' % clf.score(x, y)
    else:
        print('train first')
        return 'no model here'

@app.route('/train/delete', methods=['GET'])
def delete_train():
    try:
        shutil.rmtree('model')
        os.makedirs(model_directory)
        return 'Model wiped'

    except Exception as e:
        print(e)
        return 'Could not remove and recreate the model directory'


if __name__ == '__main__':
    try:
        port = int(sys.argv[1])
    except Exception as e:
        port = 8080

    try:
        clf = joblib.load(model_file_name)
        print('model loaded')
        model_columns = joblib.load(model_columns_file_name)
        print('model columns loaded')

    except Exception as e:
        print('No model here')
        print('Train first')
        print(str(e))
        clf = None

    app.run(host='0.0.0.0', port=port, debug=True)
