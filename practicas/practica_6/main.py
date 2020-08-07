from hardware import *
from so import *
import log
import time

##
##  MAIN
##

if __name__ == '__main__':
    log.setupLogger()
    log.logger.info('Starting emulator')
    time.sleep(0.5)
    seleccion = None
    quantum = None
    estadoDiagramaGantt = None
    frameSize = None
    tamañoMemoria = None
    print("Seleccione un número de scheduler: 1 - Expropiativo, 2 - NoExpropiativo, 3 - FCFS, 4 - RoundRobin")
    while seleccion is None:
        seleccion = input()
        if seleccion.isdigit():
            if not 1 <= int(seleccion) <= 4:
                print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
                seleccion = None
        else:
            print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
            seleccion = None
    if seleccion == "1":
        scheduler = "Expropiativo"
    if seleccion == "2":
        scheduler = "NoExpropiativo"
    if seleccion == "3":
        scheduler = "FCFS"
    if seleccion == "4":
        print("Asigne un quantum")
        quantum = input()
        scheduler = "RoundRobin con quantum = "+str(quantum)
    time.sleep(0.5)
    print("Seleccionaste "+str(scheduler))
    time.sleep(0.5)
    print("Mostrar diagrama de Gant: 1 - Si, 2 - No")
    while estadoDiagramaGantt is None:
        estadoDiagramaGantt = input()
        if estadoDiagramaGantt.isdigit():
            if not (1 == int(estadoDiagramaGantt) or 2 == int(estadoDiagramaGantt)):
                print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
                estadoDiagramaGantt = None
        else:
            print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
            estadoDiagramaGantt = None
    if estadoDiagramaGantt == "1":
        estadoDiagramaGantt = "Si"
    if estadoDiagramaGantt == "2":
        estadoDiagramaGantt = "No"
    time.sleep(0.5)
    print("Seleccionaste " + estadoDiagramaGantt)
    time.sleep(0.5)
    print("Seleccione un tamaño de frame:")
    while frameSize is None:
        frameSize = input()
        if frameSize.isdigit():
            if int(frameSize)<1:
                print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
                frameSize = None
        else:
            print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
            frameSize = None
    time.sleep(0.5)
    print("Seleccionaste un tamaño de frame de " + frameSize)
    time.sleep(0.5)
    print("Seleccione un tamaño de memoria (en celdas):")
    while tamañoMemoria is None:
        tamañoMemoria = input()
        if tamañoMemoria.isdigit():
            if int(frameSize) > int(tamañoMemoria):
                print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
                tamañoMemoria = None
        else:
            print("La ópcion seleccionada no es válida, por favor ingrese una ópcion nuevamente")
            tamañoMemoria = None
    time.sleep(0.5)
    print("Seleccionaste un tamaño de memoria de " + tamañoMemoria)
    time.sleep(0.5)
    ## setup our hardware and set memory size to 25 "cells"
    HARDWARE.setup(int(tamañoMemoria))

    ## Switch on computer
    HARDWARE.switchOn()

    ## new create the Operative System Kernel

    kernel = Kernel(seleccion, quantum, int(frameSize), int(tamañoMemoria))

    graficador = GraficadorGantt(kernel, estadoDiagramaGantt)

    HARDWARE.clock.addSubscriber(graficador)

    # "booteamos" el sistema operativo

    prg1 = Program("prg1.exe", [ASM.CPU(10), ASM.IO(), ASM.CPU(3), ASM.IO(), ASM.CPU(2)])
    prg2 = Program("prg2.exe", [ASM.CPU(4), ASM.IO(), ASM.CPU(1)])
    prg3 = Program("prg3.exe", [ASM.CPU(3)])

    kernel.fileSystem.write("c:/prg1.exe", prg1)
    kernel.fileSystem.write("c:/prg2.exe", prg2)
    kernel.fileSystem.write("c:/prg3.exe", prg3)

    # execute all programs
    kernel.run("c:/prg1.exe", 0)
    kernel.run("c:/prg2.exe", 2)
    kernel.run("c:/prg3.exe", 1)