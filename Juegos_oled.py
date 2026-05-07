from machine import Pin, I2C, PWM, ADC, Timer
from time import ticks_ms, ticks_diff, sleep
import ssd1306, framebuf, urandom 

#----------------------ESTADOS Y MODOS------------------------
# Constantes que se definen para mejor manejo de variables 
Estado_MENU = 0
Estado_JUEGO = 1
Estado_PAUSA = 2
Estado_GAMEOVER = 3

modo_CUBITO = 0
modo_PONG = 1
modo_HARDCORE = 2
modes = ["CUBITO", "PONG", "HARDCORE"]# lista para mostar en el menu 

# ---------------------------Variables----------------------
I2C_SCL = 22 # Define el pin 22 como el pin de reloj
I2C_SDA = 21 # Define el pin 21 como el pin de datos 
OLED_W = 128 # ancho de la  pantalla
OLED_H = 64  # alto de la pantalla 
PIN_BUZZ = 26

btn_up = Pin(12, Pin.IN, Pin.PULL_DOWN)
btn_menu = Pin(27, Pin.IN, Pin.PULL_DOWN)
btn_down = Pin(25, Pin.IN, Pin.PULL_DOWN)

i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400000) # el 0 es de identificacion, define los pines y la frecuencia 
oled = ssd1306.SSD1306_I2C(OLED_W, OLED_H, i2c) # con esto se crea un obejeto para controlar la pantalla oled con las dimensiones definidas usando el bus i2C
 
buzzer = PWM(Pin(PIN_BUZZ), freq=1, duty=0)

#------------------------------Variables Pong--------------------------
pj1 = ADC(Pin(34)) #Potenciometro 
pj1.width(ADC.WIDTH_10BIT)
 
pj2 = ADC(Pin(35)) #Potenciometro 
pj2.width(ADC.WIDTH_10BIT)

score_pe1 = 0  # inicia el marcador del jugador 1 en pong
score_pe2 = 0  # inicia el marcador del jugador 2 en pong
 
# ------------------------------ Antirebote-------------------------------------------
DEBOUNCE_MS = 200 # Tiempo antirebote 
last_up_ms = last_down_ms = last_menu_ms = 0 # Inicia en 0 los registros de tiempo de cada boton 

def read_buttons(): # Lector de botones con antirrebote 
    global last_up_ms, last_down_ms, last_menu_ms
    now = ticks_ms() # obtiene el timpo actual en milesegundos y lo guarda 
    up = down = menu = False 
    # verifica cada boton si esta en 1 y  si ha pasado el tiempo de antirrebote desde la ultima vez que se presiono
    if btn_up.value() == 1:
        if ticks_diff(now, last_up_ms) > DEBOUNCE_MS:
            last_up_ms = now
            up = True

    if btn_down.value() == 1:
        if ticks_diff(now, last_down_ms) > DEBOUNCE_MS:
            last_down_ms = now
            down = True

    if btn_menu.value() == 1:
        if ticks_diff(now, last_menu_ms) > DEBOUNCE_MS:
            last_menu_ms = now
            menu = True

    return up, down, menu # Devuelve el estado de cada boton 

#---------------------------- Juego Pong-------------------------------------
# -------------------------------------------------------
# UTILIDADES
# -------------------------------------------------------
def aabb(x1, y1, w1, h1, x2, y2, w2, h2):
    """Detecta colisión AABB entre dos rectángulos."""
    return not (x1+w1 <= x2 or x2+w2 <= x1 or y1+h1 <= y2 or y2+h2 <= y1) # Verifica si no se cumple ninguna condicion de no colision y si no se cumple alguna devuelve True si hay colision 
 
def draw_centered_text(o, y, txt):
    """Dibuja texto centrado horizontalmente en la OLED."""
    x = max(0, (OLED_W - len(txt)*8)//2)
    o.text(txt, x, y, 1)
 
# -------------------------------------------------------
# BUZZER NO BLOQUEANTE
# -------------------------------------------------------
beep_until_ms = 0  # Variable que almacena hasta que momento debe sonar el buzzer 
 
def beep(freq=880, dur_ms=80, duty=512):
    #Inicia un beep no bloqueante con frecuencia, duración y ciclo útil dados.
    global beep_until_ms
    buzzer.freq(freq)
    buzzer.duty(duty) # Volumen
    beep_until_ms = ticks_ms() + dur_ms
 
def tone_update():
    # Corta el sonido cuando termina su duración programada.
    global beep_until_ms
    if beep_until_ms and ticks_diff(ticks_ms(), beep_until_ms) >= 0:
        buzzer.duty(0) # 
        beep_until_ms = 0
 
# -------------------------------------------------------
# EFECTOS DE SONIDO
# -------------------------------------------------------
def snd_rebote_paleta():
    beep(freq=1200, dur_ms=25, duty=512)
def snd_rebote_pared():
    beep(freq=800, dur_ms=30, duty=450)
def snd_punto():
    beep(freq=280, dur_ms=250, duty=800)
def snd_victoria():
    beep(freq=1600, dur_ms=500, duty=700)
def snd_reinicio():
    beep(freq=900, dur_ms=80, duty=400)
def snd_cuenta_regresiva():
    beep(freq=600, dur_ms=60, duty=350)
def snd_salto():
    beep (freq= 850, dur_ms= 40, duty= 400)
def snd_baja():
    beep(freq= 600, dur_ms= 40,duty= 400)
 
# -------------------------------------------------------
# PELOTA
# -------------------------------------------------------
VELOCIDAD_PELOTA = 5  # Cambia este valor para ajustar velocidad

pelota = {
    "x": 60, # desde la izquierda
    "y": 30, # desde arriba 
    "w": 6,  # ancho de la pelota 
    "h": 6,  # alto de la pelota 
    "vx": -VELOCIDAD_PELOTA,
    "vy": VELOCIDAD_PELOTA
}
 
def reset_pelota(direccion):
    # Reinicia la pelota al centro con dirección hacia quien recibió el punto.
    global game_over, winner, game_over_time
    pelota["x"] = OLED_W // 2 - pelota["w"] // 2 # coloca la pelota en el centro horizontal de la pantalla 
    pelota["y"] = OLED_H // 2 - pelota["h"] // 2 # coloca la pelota en el centro vertical 
    pelota["vx"] = direccion * (VELOCIDAD_PELOTA // 2)
    pelota["vy"] = (VELOCIDAD_PELOTA // 2) if urandom.getrandbits(1) else -(VELOCIDAD_PELOTA // 2) # velocidad horizontal 
 
def mover_pelota():
    global score_pe1, score_pe2, game_over, winner, game_over_time
 
    pelota["x"] += pelota["vx"] # Actualiza la posicion x sumando la velocidad horizontal 
    pelota["y"] += pelota["vy"] # Actualiza la posicion y sumando la velocidad vertical
    
    # BORDE IZQUIERDO → Punto para Jugador 2
    if pelota["x"] + pelota["w"] <= 0: # verifica si la pelota salio completamente por el borde izquierdo 
        score_pe2 += 1
        snd_punto() # reproduce el sonido del punto anotado 
        # Verificar si esto causa game over
        if score_pe2 >= WIN_SCORE:
            game_over = True
            winner = 2
            game_over_time = ticks_ms()
            snd_victoria() 
        else: # si no se alcanza la puntacion ganadora - reinicia la pelota
            reset_pelota(2) 
        return
        
    # BORDE DERECHO → Punto para Jugador 1
    elif pelota["x"] >= OLED_W:
        score_pe1 += 1
        snd_punto()
        # Verificar si esto causa game over
        if score_pe1 >= WIN_SCORE:
            game_over = True
            winner = 1
            game_over_time = ticks_ms()
            snd_victoria()
        else:
            reset_pelota(-2)
        return
        
    # Rebotes verticales (paredes superior e inferior)
    if pelota["y"] <= 0:
        pelota["y"] = 0
        pelota["vy"] = abs(pelota["vy"])
        snd_rebote_pared()
    elif pelota["y"] + pelota["h"] >= OLED_H:
        pelota["y"] = OLED_H - pelota["h"]
        pelota["vy"] = -abs(pelota["vy"])
        snd_rebote_pared()
 
def check_collision_paletas(px, py, pw, ph):
    return aabb(px, py, pw, ph, pelota["x"], pelota["y"], pelota["w"], pelota["h"])
 
# -------------------------------------------------------
# PANTALLA DE INICIO CON CUENTA REGRESIVA
# -------------------------------------------------------
def pantalla_inicio_PONG():
    for cuenta in ["3", "2", "1", "GO!"]:
        oled.fill(0)
        draw_centered_text(oled, 10, "PONG")
        draw_centered_text(oled, 30, cuenta)
        oled.show()
        snd_cuenta_regresiva()
        inicio = ticks_ms()
        while ticks_diff(ticks_ms(), inicio) < 700:
            tone_update()
 
# -------------------------------------------------------
# CONFIGURACIÓN INICIAL
# -------------------------------------------------------
WIN_SCORE = 5
game_over = False
winner = None
game_over_time = 0

#--------------------------- Juego Cubito ----------------------------------------
# ----------------------- Sprite del jugador -------------------------------------
PLAYER = bytearray([
   0x00, 0x00,
    0x7F, 0xFE,
    0x40, 0x02,
    0x58, 0x1A,
    0x4C, 0x32,
    0x40, 0x02,
    0x4F, 0xF2,
    0x48, 0x12,
    0x78, 0x1E,
    0x00, 0x00,
    0x00, 0x00,
    0x60, 0x06,
    0x63, 0xC6,
    0x67, 0xE6,
    0x7F, 0xFE,
    0x00, 0x00
])
fb_player = framebuf.FrameBuffer(PLAYER, 16, 16, framebuf.MONO_HLSB)

OBSTACULO = bytearray([
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x30, 0x0C,
    0x0F, 0xF0,
    0x07, 0xE0,
    0x0D, 0xB0,
    0x0D, 0xB0,
    0x1F, 0xF8,
    0x1F, 0xF8,
    0x3C, 0x3C,
    0x33, 0xCC,
    0x1F, 0xF8,
    0x0F, 0xF0,
    0x3B, 0xDC,
    0x38, 0x1C
])
fb_obstaculo = framebuf.FrameBuffer(OBSTACULO, 16, 16, framebuf.MONO_HLSB)

# -------------------------Estado del juego ------------------------------
SUELO      = 44
player_y   = SUELO
vel_y      = 0
en_suelo   = True
obstacle_x = 120
score      = 0
game_over_cubito = False 

# ------------------------------Dibujo -----------------------------------
def draw_cubito():
    oled.fill(0)
    if game_over_cubito:
        msg1 = "GAME OVER"
        msg2 = "Score:" + str(score)
        oled.text(msg1, (128 - len(msg1) * 8) // 2, 20, 1)
        oled.text(msg2, (128 - len(msg2) * 8) // 2, 36, 1)
    else:
        oled.framebuf.blit(fb_player, 10, player_y)        
        oled.framebuf.blit(fb_obstaculo, obstacle_x, SUELO)  
        oled.framebuf.fill_rect(0, 61, 128, 2, 1)         
        oled.text(str(score), 110, 0, 1)
    oled.show()
    
# ---------------------------------Lógica -------------------------------------------------------
def update(timer):
    global player_y, vel_y, en_suelo, obstacle_x, score, game_over_cubito, game_over_time, Estado
    
    # leer botones
    up, down, menu = read_buttons()
    
    # Verificar botón MENU para volver al menú durante game over
    if game_over_cubito:
        if menu:
            Estado = Estado_MENU
            game_over_cubito = False
            tim.deinit()
        return
    
    # Verificar botón MENU para pausar
    if menu:
        Estado = Estado_PAUSA
        tim.deinit() 
        return
        
    # Salto
    if up and en_suelo:
        vel_y = -10
        en_suelo = False
        snd_salto()

    # Gravedad
    vel_y += 1
    player_y += vel_y

    # Toca el suelo
    if player_y >= SUELO:
        player_y = SUELO
        vel_y = 0
        en_suelo = True

    # Mover obstáculo
    obstacle_x -= 3
    if obstacle_x < 0:
        obstacle_x = 128
        score += 1

    # Colisión AABB 
    jugador_choca = (
        10 < obstacle_x + 16 and
        26 > obstacle_x and
        player_y < SUELO + 16 and
        player_y + 16 > SUELO
    )
    if jugador_choca:
        game_over_cubito = True
        game_over_time = ticks_ms()
        beep(200, 500, 800) 

    draw_cubito()

def pantalla_inicio_cubito():
    """Muestra 'PONG' y una cuenta regresiva 3-2-1 antes de iniciar."""
    for cuenta in ["3", "2", "1", "GO!"]:
        oled.fill(0)
        draw_centered_text(oled, 10, "CUBITO")
        draw_centered_text(oled, 30, cuenta)
        oled.show()
        snd_cuenta_regresiva()
        
        inicio = ticks_ms()
        while ticks_diff(ticks_ms(), inicio) < 700:
            tone_update()





#--------------------------- Juego Cubito Hardcore ----------------------------------------
# -----------------------------Sprite del jugador -------------------------------------
PLAYER_H = bytearray([
   0x00, 0x00,
    0x7F, 0xFE,
    0x40, 0x02,
    0x58, 0x1A,
    0x4C, 0x32,
    0x40, 0x02,
    0x4F, 0xF2,
    0x48, 0x12,
    0x78, 0x1E,
    0x00, 0x00,
    0x00, 0x00,
    0x60, 0x06,
    0x63, 0xC6,
    0x67, 0xE6,
    0x7F, 0xFE,
    0x00, 0x00
])
fb_player_H = framebuf.FrameBuffer(PLAYER_H, 16, 16, framebuf.MONO_HLSB)

# Sprite agachado
PLAYER_AGACHADO_H = bytearray([
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0x7F, 0xFE,
    0x40, 0x02,
    0x58, 0x1A,
    0x40, 0x02,
    0x7F, 0xFE,
    0x00, 0x00,
    0x67, 0xE6,
    0x7F, 0xFE,
    0x00, 0x00
])
fb_player_agachado_H = framebuf.FrameBuffer(PLAYER_AGACHADO_H, 16, 16, framebuf.MONO_HLSB)

# Sprite obstáculo normal
OBSTACULO_NORMAL_H = bytearray([
  0x00, 0x00,  
  0x00, 0x00, 
  0x00, 0x00,  
  0x00, 0x00,  
  0x00, 0x00,  
  0x00, 0x00,  
  0x00, 0x00,  
  0x00, 0x00, 
  0x11, 0x10,  
  0x11, 0x10,  
  0x11, 0x10, 
  0x3B, 0xB8,  
  0x3B, 0xB8,  
  0x3B, 0xB8,  
  0x3B, 0xB8, 
  0x7F, 0xFC,  

])
fb_obstaculo_normal_H = framebuf.FrameBuffer(OBSTACULO_NORMAL_H, 16, 16, framebuf.MONO_HLSB)

# ---------------- Estado del juego -------------------------
SUELO_H = 44
ALTO_OBSTACULO_VOLADOR_H = 40  
Y_OBSTACULO_VOLADOR_H = 10    
player_y_H = SUELO_H
vel_y_H = 0
en_suelo_H = True
agachado_H = False
obstacle_x_H = 120
obstacle_tipo_H = 0  
score_H = 0
game_over_cubito_H = False 

# ------------ Dibujo -------
def draw_cubito_H():
    oled.fill(0)
    if game_over_cubito_H:
        msg1_H = "GAME OVER"
        msg2_H = "Score:" + str(score_H)
        oled.text(msg1_H, (128 - len(msg1_H) * 8) // 2, 20, 1)
        oled.text(msg2_H, (128 - len(msg2_H) * 8) // 2, 36, 1)
    else:
        if agachado_H:
            oled.framebuf.blit(fb_player_agachado_H, 10, SUELO_H)
        else:
            oled.framebuf.blit(fb_player_H, 10, player_y_H)
        
        # Dibujar obstáculo según tipo
        if obstacle_tipo_H == 0:  # Obstáculo normal con sprite
            oled.framebuf.blit(fb_obstaculo_normal_H, obstacle_x_H, SUELO_H)
        else:  # Obstáculo volador
            oled.framebuf.fill_rect(obstacle_x_H, Y_OBSTACULO_VOLADOR_H, 8, ALTO_OBSTACULO_VOLADOR_H, 1)
        
        oled.framebuf.fill_rect(0, 61, 128, 2, 1)  
        oled.text(str(score_H), 110, 0, 1)
    oled.show()

# ── Lógica ────────────────────────────────────────
def update_H(timer_H):
    global player_y_H, vel_y_H, en_suelo_H, agachado_H, obstacle_x_H, obstacle_tipo_H, score_H, game_over_cubito_H, game_over_time_H, Estado
    
    #leer botones
    up_H, down_H, menu_H = read_buttons()
    
    # Verificar botón MENU para volver al menú durante game over
    if game_over_cubito_H:
        if menu_H:
            Estado = Estado_MENU
            game_over_cubito_H = False
            tim.deinit()
        return
    
    # Verificar botón MENU para pausar
    if menu_H:
        Estado = Estado_PAUSA
        tim.deinit()
        return
    
    # Control de agacharse
    if down_H and en_suelo_H:
        agachado_H = not agachado_H
        snd_baja()
        
    # Salto
    if up_H and en_suelo_H and not agachado_H:
        vel_y_H = -10
        en_suelo_H = False
        snd_salto()

    # Gravedad 
    if not agachado_H:
        vel_y_H += 1
        player_y_H += vel_y_H

    # Toca el suelo
    if player_y_H >= SUELO_H:
        player_y_H = SUELO_H
        vel_y_H = 0
        en_suelo_H = True

    # Mover obstáculo
    obstacle_x_H -= 5               
    if obstacle_x_H < 0:
        obstacle_x_H = 128
        score_H += 1
        obstacle_tipo_H = urandom.randint(0, 1)

    # Colisión 
    jugador_choca_H = False
    
    if obstacle_tipo_H == 0:  # Obstáculo normal
        # SIEMPRE colisiona
        jugador_choca_H = (
            10 < obstacle_x_H + 16 and
            26 > obstacle_x_H and
            player_y_H < SUELO_H + 16 and
            player_y_H + 16 > SUELO_H
        )
    else:  # Obstáculo volador
        if agachado_H:
            jugador_choca_H = False  # Agachado
        else:
            # Jugador parado colisiona con obstáculo volador
            jugador_choca_H = (
                10 < obstacle_x_H + 8 and
                26 > obstacle_x_H and
                player_y_H < Y_OBSTACULO_VOLADOR_H + ALTO_OBSTACULO_VOLADOR_H and
                player_y_H + 16 > Y_OBSTACULO_VOLADOR_H
            )
    
    if jugador_choca_H:
        game_over_cubito_H = True
        game_over_time_H = ticks_ms()
        beep(200, 500, 800)  

    draw_cubito_H()

def draw_pause_screen():
    oled.fill(0)
    draw_centered_text(oled, 20, "PAUSA")
    draw_centered_text(oled, 35, "MENU: Continuar")
    draw_centered_text(oled, 45, "UP/DOWN: Salir")
    oled.show() 

def pantalla_inicio_HARDCORE():
    """Muestra 'PONG' y una cuenta regresiva 3-2-1 antes de iniciar."""
    for cuenta in ["3", "2", "1", "GO!"]:
        oled.fill(0)
        draw_centered_text(oled, 10, "HARDCORE")
        draw_centered_text(oled, 30, cuenta)
        oled.show()
        snd_cuenta_regresiva()
        # Espera bloqueante solo en el inicio
        inicio = ticks_ms()
        while ticks_diff(ticks_ms(), inicio) < 700:
            tone_update()
#-------------------- Funciones del Menu --------------------------------------------
def draw_menu():
    oled.fill(0)
    titulo = 'SELECCIONA JUEGO'
    x_titulo = (OLED_W - len(titulo)*8) // 2
    oled.text(titulo, x_titulo, 5, 1)

    for i in range(len(modes)):
        y_pos = 25 + i * 12 
        if i == modo_idx:
            oled.text(">", 15, y_pos, 1)
            oled.text(modes[i], 25, y_pos, 1)
        else:
            oled.text(modes[i], 25, y_pos, 1)
    oled.show()

def iniciar_juego(modo):
    global Estado, modo_actual, score_pe1, score_pe2, game_over
    global player_y, vel_y, en_suelo, obstacle_x, score, game_over_cubito

    modo_actual = modo
    Estado = Estado_JUEGO

    try:
        tim.deinit()
    except:
        pass

    if modo == modo_PONG:
        # Resetear PONG
        score_pe1 = 0
        score_pe2 = 0
        game_over = False
        winner = None
        reset_pelota(-2)
        pantalla_inicio_PONG()
        snd_reinicio()
    elif modo == modo_CUBITO:
        # Resetear CUBITO
        player_y = SUELO
        vel_y = 0
        en_suelo = True
        obstacle_x = 120
        score = 0
        game_over_cubito = False
        pantalla_inicio_cubito()
        snd_reinicio()
        tim.init(period=33, mode=Timer.PERIODIC, callback=update)
    elif modo == modo_HARDCORE:
        global game_over_cubito_H, score_H, player_y_H, vel_y_H, en_suelo_H
        global agachado_H, obstacle_x_H, obstacle_tipo_H
        global game_over_time_H

        player_y_H        = SUELO_H
        vel_y_H           = 0
        en_suelo_H        = True
        agachado_H        = False
        obstacle_x_H      = 128
        obstacle_tipo_H   = 0
        score_H           = 0
        game_over_cubito_H = False
        pantalla_inicio_HARDCORE()
        snd_reinicio()
        tim.init(period=33, mode=Timer.PERIODIC, callback=update_H)

#-------------------------- Principal---------------------------------
Estado = Estado_MENU
modo_idx = 0
modo_actual = modo_CUBITO
game_over_cubito = False
game_over_time = 0

tim = Timer(0)
tim.deinit()

last_draw_ms = 0

while True:
    now = ticks_ms()
    up, down, menu = read_buttons()
    tone_update()

    if Estado == Estado_MENU:
        if up:
            modo_idx = (modo_idx - 1) % len(modes)
            beep(1000, 30, 500)
        if down:
            modo_idx = (modo_idx + 1) % len(modes)
            beep(800, 30, 500)
        if menu:
            iniciar_juego(modo_idx)
            beep(1200, 60, 600)
            continue

        # Dibujar menú cada 100ms para evitar parpade
        if ticks_diff(now, last_draw_ms) >= 100:
            draw_menu()
            last_draw_ms = now
        
        
        wait_start = ticks_ms()
        while ticks_diff(ticks_ms(), wait_start) < 10:
            tone_update()
            
    elif Estado == Estado_PAUSA:
        # Mostrar pantalla de pausa
        if ticks_diff(now, last_draw_ms) >= 500:
            draw_pause_screen()
            last_draw_ms = now
        
        # MENU: Continuar jugando
        if menu:
            Estado = Estado_JUEGO
            if modo_actual == modo_CUBITO:
                tim.init(period=33, mode=Timer.PERIODIC, callback=update)
                beep(1000, 50, 500)
            elif modo_actual==modo_HARDCORE:
                tim.init(period=33, mode=Timer.PERIODIC, callback=update_H)
                beep(1000, 50, 500)
        
        # UP o DOWN: Salir al menú principal
        if up or down:
            Estado = Estado_MENU
            game_over = False
            game_over_cubito = False
            game_over_cubito_H = False
            score_pe1 = 0
            score_pe2 = 0
            winner = None
            tim.deinit()
            beep(800, 100, 400)
        
        wait_start = ticks_ms()
        while ticks_diff(ticks_ms(), wait_start) < 50:
            tone_update()   
                     
    elif Estado == Estado_JUEGO:
        if modo_actual == modo_PONG:
            # Verificar game over 
            if game_over:
                if ticks_diff(now, game_over_time) > 2000:
                    Estado = Estado_MENU
                    game_over = False
                    score_pe1 = 0
                    score_pe2 = 0
                    winner = None
                    tim.deinit()
                    draw_menu()
                else:
                    # Mostrar pantalla de game over
                    if ticks_diff(now, last_draw_ms) >= 500:
                        oled.fill(0)
                        if winner == 1:
                            draw_centered_text(oled, 20, "JUGADOR 1")
                            draw_centered_text(oled, 30, "GANADOR!")
                        else:
                            draw_centered_text(oled, 20, "JUGADOR 2")
                            draw_centered_text(oled, 30, "GANADOR!")
                        oled.text(f"{score_pe1} - {score_pe2}", 40, 45, 1)
                        oled.show()
                        last_draw_ms = now
                
                # Permitir volver con MENU
                if menu:
                    Estado = Estado_MENU
                    game_over = False
                    score_pe1 = 0
                    score_pe2 = 0
                    winner = None
                    tim.deinit()
                
                # Delay y continuar
                wait_start = ticks_ms()
                while ticks_diff(ticks_ms(), wait_start) < 20:
                    tone_update()
                continue
            
            # Pausar con MENU durante el juego
            if menu:
                Estado = Estado_PAUSA
                continue
            
            # Juego normal
            raw1 = pj1.read()
            raw2 = pj2.read()

            px1 = 10
            px2 = 113
            py1 = int((raw1 / 1023) * (OLED_H - 25))
            py2 = int((raw2 / 1023) * (OLED_H - 25))
            pw = 5
            ph = 25
            
            mover_pelota()
                
            # Colisiones 
            if not game_over:
                if check_collision_paletas(px1, py1, pw, ph):
                    pelota["vx"] = abs(pelota["vx"]) + 0.5
                    pelota["x"] = px1 + pw
                    snd_rebote_paleta()
                elif check_collision_paletas(px2, py2, pw, ph):
                    pelota["vx"] = -abs(pelota["vx"]) - 0.5
                    pelota["x"] = px2 - pelota["w"]
                    snd_rebote_paleta()
            
            # Dibujar
            oled.fill(0)
            oled.fill_rect(px1, py1, pw, ph, 1)
            oled.fill_rect(px2, py2, pw, ph, 1)
            oled.fill_rect(int(pelota["x"]), int(pelota["y"]), pelota["w"], pelota["h"], 1)
            oled.text(f"{score_pe1}", 40, 0, 1)
            oled.text("-", 64, 0, 1)
            oled.text(f"{score_pe2}", 88, 0, 1)
            oled.show()
            
            # Delay
            wait_start = ticks_ms()
            while ticks_diff(ticks_ms(), wait_start) < 20:
                tone_update()
                
        else:  # Modo CUBITO o HARDCORE
            # Pausar con MENU
                
            if game_over_cubito:
                # Mostrar game over
                if ticks_diff(now, last_draw_ms) >= 500:
                    oled.fill(0)
                    draw_centered_text(oled, 20, "GAME OVER")
                    draw_centered_text(oled, 30, f"Score: {score}")
                    draw_centered_text(oled, 45, "MENU: Salir")
                    oled.show()
                    last_draw_ms = now
                
                # Permitir volver al menú con el botón MENU
                if menu:
                    Estado = Estado_MENU
                    game_over_cubito = False
                    tim.deinit()
                    continue
                
                # También volver automáticamente después de 2 segundos
                if ticks_diff(now, game_over_time) > 2000:
                    Estado = Estado_MENU
                    game_over_cubito = False
                    tim.deinit()
                    draw_menu()
                    
                wait_start = ticks_ms()
                while ticks_diff(ticks_ms(), wait_start) < 50:
                    tone_update()
                continue
            

            wait_start = ticks_ms()
            while ticks_diff(ticks_ms(), wait_start) < 10:
                tone_update()


