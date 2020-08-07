from hardware import *
from so import *
import log
import time

##
##  MAIN 
##
from practicas.practica_4.so import GraficadorGant

if __name__ == '__main__':
    log.setupLogger()
    log.logger.info('Starting emulator')
    time.sleep(0.5)
    seleccion = None
    quantum = None
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
    time.sleep(1.5)


    ## setup our hardware and set memory size to 25 "cells"
    HARDWARE.setup(51)

    ## Switch on computer
    HARDWARE.switchOn()

    ## new create the Operative System Kernel

    kernel = Kernel(seleccion, quantum)

    # grafico cant

    graficador = GraficadorGant(kernel)
    HARDWARE.clock.addSubscriber(graficador)

    # "booteamos" el sistema operativo

    #prg1 = Program("prg1.exe", [ASM.CPU(2)])
    #prg2 = Program("prg2.exe", [ASM.CPU(6)])
    #prg3 = Program("prg3.exe", [ASM.CPU(3)])
    prg1 = Program("prg1.exe", [ASM.CPU(2), ASM.IO(), ASM.CPU(3), ASM.IO(), ASM.CPU(2)])
    prg2 = Program("prg2.exe", [ASM.CPU(4), ASM.IO(), ASM.CPU(1)])
    prg3 = Program("prg3.exe", [ASM.CPU(3)])

    # execute all programs
    kernel.run(prg1, 3)  ## 3 = prioridad del proceso
    kernel.run(prg2, 2)  ## 2 = prioridad del proceso
    kernel.run(prg3, 1)  ## 1 = prioridad del proceso
    #kernel.run(prg4, 2)  ## 2 = prioridad del proceso
    #kernel.run(prg5, 4)  ## 4 = prioridad del proceso
    #kernel.run(prg6, 4)  ## 4 = prioridad del proceso