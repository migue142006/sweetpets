from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'super_secret_key_sweetpets'

# Base de datos simulada
users_db = {'admin': 'admin123', 'gerente': 'gerente2026'}

# Cambiamos el inventario de prueba para que tenga sentido con SweetPets
inventory = [
    {'id': 1, 'nombre': 'Comida para Perro 1kg', 'cantidad': 20}, 
    {'id': 2, 'nombre': 'Juguete de Gato', 'cantidad': 15}
]

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Validar credenciales
        if username in users_db and users_db[username] == password:
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales incorrectas. Intente nuevamente.')
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    # Mensaje de bienvenida actualizado a SweetPets
    return f"<h1 style='text-align:center;'>🐾 Bienvenido a SweetPets</h1><p style='text-align:center;'>Inventario actual: {inventory}</p>"

@app.route('/registro')
def registro():
    # Ruta temporal para el botón de registrarse
    return "<h1 style='text-align:center;'>Página de Registro</h1><p style='text-align:center;'>El módulo de registro estará disponible en el próximo entregable.</p><div style='text-align:center;'><a href='/'>Volver al Login</a></div>"

if __name__ == '__main__':
    app.run(debug=True)
