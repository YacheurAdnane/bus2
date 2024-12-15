from flask import Flask, render_template, request, jsonify, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import json

app = Flask(__name__)

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

@app.route('/')
def index():
    # Fetch wilayas from Firestore
    wilayas_ref = db.collection('wilayas')
    wilayas_docs = list(wilayas_ref.stream())
    wilayas = [doc.id for doc in wilayas_docs]

    # Get the selected stop (default to None)
    selected_stop = request.args.get('stop', None)

    # Fetch lines based on the selected stop
    lines = []
    if selected_stop:
        for wilaya_doc in wilayas_docs:
            wilaya = wilaya_doc.id
            lines_ref = wilaya_doc.reference.collection('lines')
            for line_doc in lines_ref.stream():
                line_data = line_doc.to_dict()
                stops = line_data.get('stops', [])
                if any(stop['name'] == selected_stop for stop in stops):
                    lines.append({
                        "wilaya": wilaya,
                        "name": line_doc.id,
                        "stops": stops,
                        "color": line_data['color']
                    })
    
    return render_template('index.html', wilayas=wilayas, selected_stop=selected_stop, lines=lines)


@app.route('/add_line')
def add_line():
    wilayas_ref = db.collection('wilayas')
    wilayas_docs = list(wilayas_ref.stream())
    wilayas = [doc.id for doc in wilayas_docs]
    return render_template('add_line.html', wilayas=wilayas)

@app.route('/stops/<wilaya>')
def get_wilaya_stops(wilaya):
    # Fetch stops for a specific wilaya
    stops_ref = db.collection('wilayas').document(wilaya).collection('stops')
    
    print(stops_ref)
    stops = []
    
    for doc in stops_ref.stream():
        stop = doc.to_dict()
        stop['name'] = doc.id
        stops.append(stop)
    
    # Get coordinates for the wilaya
    if stops:
        coordinates = {"lat": float(stops[0]['lat']), "lon": float(stops[0]['lon'])}
    else:
        coordinates = {"lat": 28.0339, "lon": 1.6596}  # Default center of Algeria
    
    return jsonify({"stops": stops, "coordinates": coordinates})

@app.route('/lines/<stop_name>')
def get_stop_lines(stop_name):
    # Fetch lines containing the specific stop
    lines = []
    wilayas_ref = db.collection('wilayas')
    wilayas_docs = list(wilayas_ref.stream())
    
    for wilaya_doc in wilayas_docs:
        wilaya_lines_ref = wilaya_doc.reference.collection('lines')
        
        for line_doc in wilaya_lines_ref.stream():
            line_data = line_doc.to_dict()
            stops = line_data.get('stops', [])
            
            if any(stop['name'] == stop_name for stop in stops):
                lines.append({
                    "name": line_doc.id,
                    "stops": stops
                })
    
    return jsonify({"lines": lines})

@app.route('/get_wilaya_stops', methods=['POST'])
def fetch_wilaya_stops():
    wilaya = request.json.get('wilaya')
    stops_ref = db.collection('wilayas').document(wilaya).collection('stops')
    print(stops_ref.stream())
    stops = []
    for doc in stops_ref.stream():
        stop = doc.to_dict()
        stop['name'] = doc.id
        stops.append(stop)
    
    return jsonify(stops)

@app.route('/save_line', methods=['POST'])
def save_line():
    data = request.json
    wilaya = data['wilaya']
    line_name = data['line_name']
    stops = data['stops']
    color = data['color']

    # Reference to the specific wilaya and its lines
# Check if the wilaya exists, if not, create it
    wilaya_ref = db.collection('wilayas').document(wilaya)
    wilaya_doc = wilaya_ref.get()
    if not wilaya_doc.exists:
        # Create the wilaya document
        wilaya_ref.set({})    
    lines_ref = wilaya_ref.collection('lines')
    stops_ref = wilaya_ref.collection('stops')

    # Save or update stops
    for stop in stops:
        stops_ref.document(stop['name']).set({
            'lat': stop['lat'],
            'lon': stop['lon']
        }, merge=True)

    # Save the line with its stops
    lines_ref.document(line_name).set({
        'stops': stops,
        'color': color
    })

    return jsonify({"message": "Line saved successfully!"})

@app.route('/manage_data')
def manage_data():
    wilayas_ref = db.collection('wilayas')
    wilayas_docs = list(wilayas_ref.stream())
    wilayas = [doc.id for doc in wilayas_docs]
    return render_template('manage_data.html', wilayas=wilayas)

@app.route('/get_lines/<wilaya>')
def get_lines(wilaya):
    # Fetch lines for a specific wilaya
    lines_ref = db.collection('wilayas').document(wilaya).collection('lines')
    lines = [{"name": doc.id} for doc in lines_ref.stream()]
    return jsonify({"lines": lines})

@app.route('/get_line_stops/<wilaya>/<line_name>')
def get_line_stops(wilaya, line_name):
    # Fetch stops for a specific line in a wilaya
    line_ref = db.collection('wilayas').document(wilaya).collection('lines').document(line_name)
    line_doc = line_ref.get()
    
    stops = line_doc.to_dict().get('stops', []) if line_doc.exists else []
    return jsonify({"stops": stops})

@app.route('/delete_line', methods=['POST'])
def delete_line():
    data = request.json
    wilaya = data['wilaya']
    line_name = data['line_name']
    
    # Delete the line
    line_ref = db.collection('wilayas').document(wilaya).collection('lines').document(line_name)
    line_ref.delete()
    
    return jsonify({"message": "Line deleted successfully"})

@app.route('/delete_stop', methods=['POST'])
def delete_stop():
    data = request.json
    wilaya = data['wilaya']
    stop_name = data['stop_name']
    
    # Delete stop from stops collection
    stop_ref = db.collection('wilayas').document(wilaya).collection('stops').document(stop_name)
    stop_ref.delete()
    
    # Remove stop from all lines
    lines_ref = db.collection('wilayas').document(wilaya).collection('lines')
    
    for line_doc in lines_ref.stream():
        line_data = line_doc.to_dict()
        stops = line_data.get('stops', [])
        
        # Remove stop from line if it exists
        updated_stops = [stop for stop in stops if stop['name'] != stop_name]
        
        if updated_stops:
            # Update line with remaining stops
            lines_ref.document(line_doc.id).update({'stops': updated_stops})
        else:
            # Delete line if no stops remain
            lines_ref.document(line_doc.id).delete()
    
    return jsonify({"message": "Stop deleted successfully"})

@app.route('/remove_stop_from_line', methods=['POST'])
def remove_stop_from_line():
    data = request.json
    wilaya = data['wilaya']
    line_name = data['line_name']
    stop_name = data['stop_name']
    
    # Reference to the specific line
    line_ref = db.collection('wilayas').document(wilaya).collection('lines').document(line_name)
    line_doc = line_ref.get()
    
    if line_doc.exists:
        line_data = line_doc.to_dict()
        stops = line_data.get('stops', [])
        
        # Remove the specific stop
        updated_stops = [stop for stop in stops if stop['name'] != stop_name]
        
        if updated_stops:
            # Update line with remaining stops
            line_ref.update({'stops': updated_stops})
            return jsonify({"message": "Stop removed from line successfully"})
        else:
            # Delete line if no stops remain
            line_ref.delete()
            return jsonify({"message": "Line deleted as it had no remaining stops"})
    
    return jsonify({"error": "Line not found"}), 404
# Alternative debugging method
def debug_firestore_collection(collection_name):
    """
    Helper function to debug Firestore collection
    """
    collection_ref = db.collection(collection_name)
    docs = list(collection_ref.stream())
    
    print(f"Debug for collection: {collection_name}")
    print(f"Total documents: {len(docs)}")
    
    for doc in docs:
        print(f"Document ID: {doc.id}")
        print(f"Document Data: {doc.to_dict()}")
        print("---")

# Add this route for manual debugging
@app.route('/debug_firestore')
def debug_firestore():
    debug_firestore_collection('wilayas')
    return "Check console for Firestore debug information"
if __name__ == '__main__':
    app.run(debug=True)