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

# In app.py, update the get_stop_lines route:



# Get stop lines route
@app.route('/lines/<wilaya>/<stop_name>')
def get_stop_lines(wilaya, stop_name):
    """
    Fetch lines containing the specific stop for a specific wilaya
    """
    try:
        lines = []
        wilaya_ref = db.collection('wilayas').document(wilaya)
        lines_ref = wilaya_ref.collection('lines')
        
        for line_doc in lines_ref.stream():
            line_data = line_doc.to_dict()
            stops_collection = line_doc.reference.collection('stops')
            
            # Get all stops for this line
            stops = []
            for stop_doc in stops_collection.order_by('order').stream():
                stop_data = stop_doc.to_dict()
                stops.append({
                    'name': stop_data['name'],
                    'lat': stop_data['lat'],
                    'lon': stop_data['lon']
                })
            
            # Check if the requested stop is in this line
            if any(stop['name'] == stop_name for stop in stops):
                lines.append({
                    "name": line_doc.id,
                    "stops": stops,
                    "color": line_data.get('color', '#3388ff')
                })
        
        return jsonify({"lines": lines})
        
    except Exception as e:
        print(f"Error getting stop lines: {str(e)}")
        return jsonify({
            "message": f"Error getting stop lines: {str(e)}",
            "status": "error",
            "lines": []
        }), 500
    

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
    try:
        data = request.json
        wilaya = data['wilaya']
        line_name = data['line_name']
        stops = data['stops']
        color = data['color']
        route_geometries = data.get('route_geometries', [])

        # Create references for the new structure
        wilaya_ref = db.collection('wilayas').document(wilaya)
        
        # Ensure wilaya document exists
        if not wilaya_ref.get().exists:
            wilaya_ref.set({})

        # Save common stops in wilaya/stops collection
        stops_ref = wilaya_ref.collection('stops')
        for stop in stops:
            stop_data = {
                'lat': str(stop['lat']),
                'lon': str(stop['lon'])
            }
            stops_ref.document(stop['name']).set(stop_data, merge=True)

        # Create line document with metadata
        line_ref = wilaya_ref.collection('lines').document(line_name)
        line_data = {
            'color': color,
            'created_at': firestore.SERVER_TIMESTAMP,
            'stops_count': len(stops)
        }
        line_ref.set(line_data)

        # Create stops subcollection for the line
        stops_collection = line_ref.collection('stops')
        for i, stop in enumerate(stops):
            stop_data = {
                'name': str(stop['name']),
                'lat': str(stop['lat']),
                'lon': str(stop['lon']),
                'order': i
            }
            stops_collection.document(str(i)).set(stop_data)

        # Create route subcollection with serialized route data
        if route_geometries:
            route_collection = line_ref.collection('route')
            for i, geometry in enumerate(route_geometries):
                # Convert the route geometry to a serializable format
                serialized_coordinates = []
                for coord in geometry['coordinates']:
                    # Store each coordinate pair as a string
                    coord_str = f"{coord[0]},{coord[1]}"
                    serialized_coordinates.append(coord_str)
                
                route_data = {
                    'type': geometry['type'],
                    'coordinates': serialized_coordinates,
                    'order': i
                }
                route_collection.document(str(i)).set(route_data)

        return jsonify({
            "message": "Line saved successfully!",
            "status": "success",
            "wilaya": wilaya,
            "line": line_name
        })

    except Exception as e:
        print(f"Error saving line: {str(e)}")
        return jsonify({
            "message": f"Error saving line: {str(e)}",
            "status": "error"
        }), 500

@app.route('/get_line_stops/<wilaya>/<line_name>')
def get_line_stops(wilaya, line_name):
    try:
        line_ref = db.collection('wilayas').document(wilaya).collection('lines').document(line_name)
        
        line_doc = line_ref.get()
        if not line_doc.exists:
            return jsonify({"stops": [], "route_geometries": [], "color": '#3388ff'})
        
        line_data = line_doc.to_dict()
        
        # Get stops
        stops = []
        stops_collection = line_ref.collection('stops')
        for stop_doc in stops_collection.order_by('order').stream():
            stop_data = stop_doc.to_dict()
            stops.append({
                'name': stop_data['name'],
                'lat': stop_data['lat'],
                'lon': stop_data['lon']
            })
        
        # Get and deserialize route geometries
        route_geometries = []
        route_collection = line_ref.collection('route')
        for route_doc in route_collection.order_by('order').stream():
            route_data = route_doc.to_dict()
            
            # Deserialize coordinates
            coordinates = []
            for coord_str in route_data['coordinates']:
                lon, lat = map(float, coord_str.split(','))
                coordinates.append([lon, lat])
            
            geometry = {
                'type': route_data['type'],
                'coordinates': coordinates
            }
            route_geometries.append(geometry)
        
        return jsonify({
            "stops": stops,
            "route_geometries": route_geometries,
            "color": line_data.get('color', '#3388ff')
        })
        
    except Exception as e:
        print(f"Error getting line stops: {str(e)}")
        return jsonify({
            "message": f"Error getting line stops: {str(e)}",
            "status": "error",
            "stops": [],
            "route_geometries": [],
            "color": '#3388ff'
        }), 500

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


@app.route('/delete_line', methods=['POST'])
def delete_line():
    data = request.json
    wilaya = data['wilaya']
    line_name = data['line_name']
    
    try:
        # Get reference to the line document
        line_ref = db.collection('wilayas').document(wilaya).collection('lines').document(line_name)
        
        # Delete all stops in the line's stops subcollection
        stops_collection = line_ref.collection('stops')
        for stop_doc in stops_collection.stream():
            stop_doc.reference.delete()
            
        # Delete all routes in the line's route subcollection
        route_collection = line_ref.collection('route')
        for route_doc in route_collection.stream():
            route_doc.reference.delete()
            
        # Finally delete the line document itself
        line_ref.delete()
        
        return jsonify({"message": "Line and all associated data deleted successfully"})
        
    except Exception as e:
        print(f"Error deleting line: {str(e)}")
        return jsonify({
            "message": f"Error deleting line: {str(e)}",
            "status": "error"
        }), 500

@app.route('/delete_stop', methods=['POST'])
def delete_stop():
    data = request.json
    wilaya = data['wilaya']
    stop_name = data['stop_name']
    
    try:
        # Delete stop from wilaya's stops collection
        stop_ref = db.collection('wilayas').document(wilaya).collection('stops').document(stop_name)
        stop_ref.delete()
        
        # Get all lines in the wilaya
        lines_ref = db.collection('wilayas').document(wilaya).collection('lines')
        for line_doc in lines_ref.stream():
            line_ref = line_doc.reference
            
            # Check stops subcollection for the stop to delete
            stops_collection = line_ref.collection('stops')
            stops_to_delete = []
            remaining_stops = []
            order = 0
            
            for stop_doc in stops_collection.order_by('order').stream():
                stop_data = stop_doc.to_dict()
                if stop_data['name'] == stop_name:
                    stops_to_delete.append(stop_doc.reference)
                else:
                    # Update order of remaining stops
                    stop_doc.reference.update({'order': order})
                    remaining_stops.append(stop_data)
                    order += 1
            
            # Delete the stop documents
            for stop_ref in stops_to_delete:
                stop_ref.delete()
            
            # Update the line's stops count
            line_ref.update({'stops_count': len(remaining_stops)})
            
            # If no stops remain, delete the entire line
            if len(remaining_stops) == 0:
                # Delete route subcollection
                for route_doc in line_ref.collection('route').stream():
                    route_doc.reference.delete()
                # Delete the line document
                line_ref.delete()
        
        return jsonify({"message": "Stop deleted successfully from wilaya and all associated lines"})
        
    except Exception as e:
        print(f"Error deleting stop: {str(e)}")
        return jsonify({
            "message": f"Error deleting stop: {str(e)}",
            "status": "error"
        }), 500

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