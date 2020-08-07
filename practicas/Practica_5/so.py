#!/usr/bin/env python

from hardware import *
from main import *
import log

## emulates a compiled program
from tabulate import tabulate


class Program:

    def __init__(self, name, instructions):
        self._name = name
        self._instructions = self.expand(instructions)

    @property
    def name(self):
        return self._name

    @property
    def instructions(self):
        return self._instructions

    def addInstr(self, instruction):
        self._instructions.append(instruction)

    def expand(self, instructions):
        expanded = []
        for i in instructions:
            if isinstance(i, list):
                ## is a list of instructions
                expanded.extend(i)
            else:
                ## a single instr (a String)
                expanded.append(i)

        ## now test if last instruction is EXIT
        ## if not... add an EXIT as final instruction
        last = expanded[-1]
        if not ASM.isEXIT(last):
            expanded.append(INSTRUCTION_EXIT)

        return expanded

    def __repr__(self):
        return "Program({name}, {instructions})".format(name=self._name, instructions=self._instructions)


## emulates an Input/Output device controller (driver)
class IoDeviceController():

    def __init__(self, device):
        self._device = device
        self._waiting_queue = []
        self._currentPCB = None

    def runOperation(self, pcb, instruction):
        pair = {'pcb': pcb, 'instruction': instruction}
        # append: adds the element at the end of the queue
        self._waiting_queue.append(pair)
        # try to send the instruction to hardware's device (if is idle)
        self.__load_from_waiting_queue_if_apply()

    def getFinishedPCB(self):
        finishedPCB = self._currentPCB
        self._currentPCB = None
        self.__load_from_waiting_queue_if_apply()
        return finishedPCB

    def __load_from_waiting_queue_if_apply(self):
        if (len(self._waiting_queue) > 0) and self._device.is_idle:
            ## pop(): extracts (deletes and return) the first element in queue
            pair = self._waiting_queue.pop(0)
            # print(pair)
            pcb = pair['pcb']
            instruction = pair['instruction']
            self._currentPCB = pcb
            self._device.execute(instruction)

    def __repr__(self):
        return "IoDeviceController for {deviceID} running: {currentPCB} waiting: {waiting_queue}".format(
            deviceID=self._device.deviceId, currentPCB=self._currentPCB, waiting_queue=self._waiting_queue)


## ############################## SCHEDULERS ########################################
## ############################## ABSTRACT SCHEDULER ########################################

class AbstractScheduler:

    def __init__(self):
        self._readyQueue = ReadyQueue()

    @property
    def readyQueue(self):
        return self._readyQueue

    def mustExpropiate(self, pcb, pcbInCpu):
        return False


################################ FCFS SCHEDULER ########################################


class FCFSScheduler(AbstractScheduler):

    def getPcb(self):
        return self.readyQueue.getNextPcb()


################################ ROUND ROBIN SCHEDULER ########################################


class RoundRobinScheduler(AbstractScheduler):

    def __init__(self, quantum):
        self._readyQueue = ReadyQueue()
        HARDWARE.timer.quantum = quantum

    def getPcb(self):
        return self.readyQueue.getNextPcb()


################################ PRIORITY SCHEDULER ########################################


class PriorityScheduler(AbstractScheduler):

    def getPcb(self):
        return self.readyQueue.getNextPcbMayorPrioridad()


################################ PRIORITY NO EXPROPIATIVO SCHEDULER ########################################


class PriorityNoExpropiativoScheduler(PriorityScheduler):
    pass


############################### PRIORITY EXPROPIATIVO SCHEDULER ########################################


class PriorityExpropiativoScheduler(PriorityScheduler):

    def mustExpropiate(self, pcb, pcbInCpu):
        return pcb.priority < pcbInCpu.priority


## emulates the  Interruptions Handlers
class AbstractInterruptionHandler():

    def __init__(self, kernel):
        self._kernel = kernel
        self._scheduler = kernel.scheduler

    @property
    def kernel(self):
        return self._kernel

    @property
    def scheduler(self):
        return self._scheduler

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))

    def handlerIn(self, pcb):
        if self.kernel.pcbTable.runningPCB is None:
            self.kernel.dispatcher.load(pcb)
            pcb.state = "running"
            self.kernel.pcbTable.runningPCB = pcb
        else:
            pcbInCpu = self.kernel.pcbTable.runningPCB
            if self.kernel.scheduler.mustExpropiate(pcb, pcbInCpu):
                pcbExpropiado = pcbInCpu
                pcbExpropiado.state = "ready"
                self.kernel.dispatcher.save(pcbExpropiado)
                self.scheduler.readyQueue.add(pcbExpropiado)
                self.kernel.dispatcher.load(pcb)
                pcb.state = "running"
                self.kernel.pcbTable.runningPCB = pcb
            else:
                pcb.state = "ready"
                self.kernel.scheduler.readyQueue.add(pcb)

    def handlerOut(self):
        if self.kernel.scheduler.readyQueue.lista:
            nextPCB = self.scheduler.getPcb()
            nextPCB.state = "running"
            self.kernel.dispatcher.load(nextPCB)
            self.kernel.pcbTable.runningPCB = nextPCB


class KillInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        log.logger.info(" Program Finished ")
        pcb = self.kernel.pcbTable.runningPCB
        self.kernel.dispatcher.save(pcb)
        pcb.state = "terminated"
        self.kernel.pcbTable.remove(pcb.pid)
        self.kernel.pcbTable.runningPCB = None
        self.handlerOut()
        self.kernel.memoryManager.liberarFrameUsado(pcb)
        if self.terminoTodosLosProcesos():
            self.kernel.finalizado = True
            HARDWARE.switchOff()

    def terminoTodosLosProcesos(self):
        resultado = True
        for pcbIndice in self.kernel.pcbTable.tabla:
            resultado = resultado and pcbIndice.state == "terminated"
        return resultado



class IoInInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        program = irq.parameters
        pcb = self.kernel.pcbTable.runningPCB
        self.kernel.pcbTable.runningPCB = None
        pcb.state = "waiting"
        self.kernel.dispatcher.save(pcb)
        self.kernel.ioDeviceController.runOperation(pcb, program)
        log.logger.info(self.kernel.ioDeviceController)
        self.handlerOut()


class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pcb = self.kernel.ioDeviceController.getFinishedPCB()
        log.logger.info(self.kernel.ioDeviceController)
        self.handlerIn(pcb)


class NewInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pathProgram = irq.parameters[0]
        priority = irq.parameters[1]
        program = self.kernel.fileSystem.read(pathProgram)
        pageTable = self.kernel.memoryManager.pageTableDePrograma(program)
        primerTupla = pageTable.table[0]
        for tuple in pageTable.table:
            self.kernel.loader.load(tuple)
        baseDir = self.kernel.memoryManager.baseDirDeFrame(primerTupla[1])
        pid = self.kernel.pcbTable.getNewPID()
        pcb = PCB(baseDir, pid, program.name, priority, pageTable)
        self.kernel.pcbTable.add(pcb)
        self.handlerIn(pcb)


class TimeoutInterruptionHandle(AbstractInterruptionHandler):

    def execute(self, irq):
        if self.scheduler.readyQueue.lista:
            pcbCorriendo = self.kernel.pcbTable.runningPCB
            pcbCorriendo.state = "ready"
            self.kernel.dispatcher.save(pcbCorriendo)
            self.scheduler.readyQueue.add(pcbCorriendo)
            self.kernel.pcbTable.runningPCB = None
            self.handlerOut()
        else:
            HARDWARE.timer.reset()


################################ LOADER ########################################


class Loader:

    def __init__(self, kernel, frameSize):
        self.kernel = kernel
        #self._kernel = kernel
        self._frameSize = frameSize

    @property
    def frameSize(self):
        return self._frameSize

    def load(self, tuple):
        # loads the program in main memory
        numeroPagina = tuple[0]
        pagina = self.kernel.memoryManager.logicalMemory.getPageForId(numeroPagina)
        numeroFrame = tuple[1]
        baseDir = self.kernel.memoryManager.baseDirDeFrame(numeroFrame)
        progSize = len(pagina.cells)
        celdaContador = baseDir
        for index in range(0, progSize):
            inst = pagina.cells[index]
            HARDWARE.memory.write(celdaContador, inst)
            celdaContador += 1

    def dividirProgramaEnPaginas(self, instrucciones):
        listaIntruccionesAgrupadas = []
        lista = []

        log.logger.info("instrucciones := {}".format(instrucciones))
        for instr in instrucciones:
            lista.append(instr)
            if len(lista) == self.frameSize:
                listaIntruccionesAgrupadas.append(lista)
                lista = []
        if lista:
            listaIntruccionesAgrupadas.append(lista)
        log.logger.info("listaIntruccionesAgrupadas := {}".format(listaIntruccionesAgrupadas))
        return listaIntruccionesAgrupadas


################################ READY QUEUE ########################################


class ReadyQueue:

    def __init__(self):
        self._lista = []

    def add(self, pcb):
        self._lista.append(pcb)

    def remove(self, pcb):
        self._lista.remove(pcb)

    @property
    def lista(self):
        return self._lista

    def getNextPcb(self):
        pcb = self.lista[0]
        self.remove(pcb)
        return pcb

    def getNextPcbMayorPrioridad(self):
        pcbBuscado = self.lista[0]
        prioridadActual = pcbBuscado.priority
        for pcb in self.lista:
            if pcb.priority < prioridadActual:
                pcbBuscado = pcb
                prioridadActual = pcbBuscado.priority
        self.remove(pcbBuscado)
        return pcbBuscado


################################ PCB ########################################


class PCB:

    def __init__(self, baseDir, pid, nombre, priority, pageTable):
        self._baseDir = baseDir
        self._pid = pid
        self._pc = 0
        self._state = "new"
        self._path = nombre
        self._priority = priority
        self._pageTable = pageTable

    @property
    def baseDir(self):
        return self._baseDir

    @property
    def priority(self):
        return self._priority

    @property
    def pid(self):
        return self._pid

    @property
    def pc(self):
        return self._pc

    @pc.setter
    def pc(self, pc):
        self._pc = pc

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        self._state = state

    @property
    def path(self):
        return self._path

    @property
    def pageTable(self):
        return self._pageTable

    def __repr__(self):
        return "PCB(pid={}, baseDir={}, pc={}, state={}, path={}, priority={})".format(self.pid, self.baseDir, self.pc, self.state, self.path, self.priority)


################################ PCBTABLE ########################################


class PCBTable:

    def __init__(self):
        self._tabla = []
        self._pid = -1
        self._runningPcb = None

    @property
    def tabla(self):
        return self._tabla

    @property
    def pid(self):
        return self._pid

    @pid.setter
    def pid(self, pid):
        self._pid = pid

    @property
    def runningPCB(self):
        return self._runningPcb

    @runningPCB.setter
    def runningPCB(self, pcb):
        self._runningPcb = pcb

    def add(self, pcb):
        self._tabla.append(pcb)

    def remove(self, pid):
        pcb = self.get(pid)
        self._tabla.remove(pcb)

    def get(self, pidBuscado):
        pcbResultado = None
        for pcb in self._tabla:
            if pcb.pid == pidBuscado:
                pcbResultado = pcb
                break
        return pcbResultado

    def getNewPID(self):
        nuevoPid = self.pid + 1
        self.pid = nuevoPid
        return nuevoPid


################################ DISPATCHER ########################################


class Dispatcher:

    def load(self, pcb):
        pageTable = pcb.pageTable
        HARDWARE.timer.reset()
        HARDWARE.cpu.pc = pcb.pc
        HARDWARE.mmu.baseDir = pcb.baseDir
        log.logger.info("loading pcb:{pcb}".format(pcb=pcb))
        HARDWARE.mmu.resetTLB()  ##nuevo
        for tuple in pageTable.table:
            HARDWARE.mmu.setPageFrame(tuple[0], tuple[1])   ##nuevo

    def save(self, pcb):
        pcb.pc = HARDWARE.cpu.pc
        HARDWARE.cpu.pc = -1
        log.logger.info("saving pcb:{pcb}".format(pcb=pcb))


################################ FILE SYSTEM ########################################

class FileSystem:       ##nuevo

    def __init__(self, kernel):
        self._files = []
        self._kernel = kernel

    def write(self, path, program):
        newFile = [path, program]
        self._files.append(newFile)

    def read(self, path):
        for file in self._files:
            if file[0] == path:
                fileBuscado = file
        return fileBuscado[1]


################################ MEMORY MANAGER ########################################

class MemoryManager:       ##nuevo

    def __init__(self, kernel, frameSize, cantidadFrames):
        self.kernel = kernel
        self._logicalMemory = LogicalMemory()
        self._frameSize = frameSize
        self._framesLibres = list(range(cantidadFrames))
        self._framesUsados = []
        #self._kernel = kernel

    @property
    def logicalMemory(self):
        return self._logicalMemory

    @property
    def frameSize(self):
        return self._frameSize

    @property
    def framesLibres(self):
        return self._framesLibres

    @property
    def framesUsados(self):
        return self._framesUsados

    def frameOfPage(self, page):
        for tuple in self.pageTable.table:
            if tuple[0] == page.id:
                frame = tuple[1]
        return frame

    def getFrameLibre(self):
        numeroFrame = self.framesLibres[0]
        self.framesUsados.append(numeroFrame)
        self.framesLibres.remove(numeroFrame)
        return numeroFrame

    def liberarFrameUsado(self, pcb):
        for tupla in pcb.pageTable.table:
            numeroFrame = tupla[1]
            self.framesLibres.append(numeroFrame)
            self.framesUsados.remove(numeroFrame)
        print("- - - - Frames libres actualizados: " + str(self.kernel.memoryManager.framesLibres) + " - - - -")

    def memoriaLibre(self):
        return len(self.framesLibres) * self.frameSize

    def baseDirDeFrame(self, numeroFrame):
        return numeroFrame * self.frameSize

    def pageTableDePrograma(self, programa):
        instrucciones = programa.instructions
        instruccionesAgrupadas = self.kernel.loader.dividirProgramaEnPaginas(instrucciones)
        pageTableNueva = PageTable()
        for grupo in instruccionesAgrupadas:
            paginaNueva = pageTableNueva.crearPagina(grupo)
            self.logicalMemory.addPage(paginaNueva)
            frameNuevo = self.getFrameLibre()
            tuple = [paginaNueva.id, frameNuevo]
            pageTableNueva.addTuple(tuple)
        return pageTableNueva


################################ LOGICAL MEMORY ########################################

class LogicalMemory:  ##nuevo

    def __init__(self):
        self._memory = [] ##paginas

    @property
    def memory(self):
        return self._memory

    def addPage(self, page):
        self.memory.append(page)

    def getPageForId(self, id):
        for page in self.memory:
            if page.id == id:
                pageBuscado = page
        return pageBuscado


################################ PAGE TABLE ########################################

class PageTable:       ##nuevo

    def __init__(self):
        self._contadorIdPages = -1
        self._table = []

    @property
    def getIdPage(self):
        self._contadorIdPages += 1
        return self._contadorIdPages

    @property
    def table(self):
        return self._table

    def addTuple(self, tuple): ## [idPage, numeroFrameMemoria]
        return self._table.append(tuple)

    def crearPagina(self, instrucciones):
        return Page(self.getIdPage, instrucciones)


################################ PAGE ########################################

class Page:  ##nuevo

    def __init__(self, id, cells):
        self._id = id
        self._cells = cells

    @property
    def cells(self):
        return self._cells

    @property
    def id(self):
        return self._id


################################ KERNEL ########################################
# emulates the core of an Operative System


class Kernel:

    def __init__(self, seleccion, quantum, frameSize, tamañoMemoria):
        self._tamañoMemoria = tamañoMemoria
        if seleccion == "1":
            self._scheduler = PriorityExpropiativoScheduler()
        if seleccion == "2":
            self._scheduler = PriorityNoExpropiativoScheduler()
        if seleccion == "3":
            self._scheduler = FCFSScheduler()
        if seleccion == "4":
            self._scheduler = RoundRobinScheduler(int(quantum))

        ## setup interruption handlers
        killHandler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, killHandler)

        ioInHandler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, ioInHandler)

        ioOutHandler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, ioOutHandler)

        newHandler = NewInterruptionHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE, newHandler)

        timeoutHandler = TimeoutInterruptionHandle(self)
        HARDWARE.interruptVector.register(TIMEOUT_INTERRUPTION_TYPE, timeoutHandler)

        ## setear frameSize al MMU
        HARDWARE.mmu.frameSize = int(frameSize)

        ## controls the Hardware's I/O Device
        self._finalizado = None
        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)
        self._loader = Loader(self, frameSize)
        self._pcbTable = PCBTable()
        self._dispatcher = Dispatcher()
        self.memoryManager = MemoryManager(self, frameSize, int(tamañoMemoria / frameSize))
        self.fileSystem = FileSystem(self)

    @property
    def memoryManager(self):
        return self._memoryManager

    @property
    def fileSystem(self):
        return self._fileSystem

    @property
    def finalizado(self):
        return self._finalizado

    @finalizado.setter
    def finalizado(self, finalizado):
        self._finalizado = finalizado

    @property
    def ioDeviceController(self):
        return self._ioDeviceController

    @property
    def tamañoMemoria(self):
        return self._tamañoMemoria

    @property
    def loader(self):
        return self._loader

    @property
    def pcbTable(self):
        return self._pcbTable

    @property
    def dispatcher(self):
        return self._dispatcher

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def diagramaGant(self):
        return self._diagramaGant

    ## emulates a "system call" for programs execution
    def run(self, pathProgram, priority):
        self.finalizado = False
        tuple = [pathProgram, priority]
        newIRQ = IRQ(NEW_INTERRUPTION_TYPE, tuple)
        HARDWARE.interruptVector.handle(newIRQ)
        log.logger.info("\n Executing program: {name}".format(name=self.fileSystem.read(pathProgram).name))
        log.logger.info(HARDWARE)

    def __repr__(self):
        return "Kernel "

    @fileSystem.setter
    def fileSystem(self, value):
        self._fileSystem = value

    @memoryManager.setter
    def memoryManager(self, value):
        self._memoryManager = value


class GraficadorGantt:

    def __init__(self, kernel, estado):
        self._kernel = kernel
        self._representacion = []
        self._headers = ["procesos"]
        self._activo = estado

    @property
    def representacion(self):
        return self._representacion

    @representacion.setter
    def representacion(self, representacion):
        self._representacion = representacion

    @property
    def activo(self):
        return self._activo

    @activo.setter
    def activo(self, activo):
        self._activo = activo

    @property
    def kernel(self):
        return self._kernel

    def tick(self, ticknum):
        if ticknum == 1:
            self.representacion = self.cuadro(self.kernel.pcbTable.tabla)
            self.actualizarRepresentacion(ticknum, self.kernel.pcbTable.tabla)

        if ticknum > 1:
            self.actualizarRepresentacion(ticknum, self._kernel.pcbTable.tabla)

        if (self.activo == "Si") and (self.kernel.finalizado is True):
            log.logger.info(self.__repr__())
            self.activo = "No"

    def actualizarRepresentacion(self, ticknum, pcbTable):
        self._headers.append(ticknum)

        nroProceso = 0

        for pcb in pcbTable:
            retorna = pcb.state
            self._representacion[nroProceso].append(retorna)

            nroProceso = nroProceso + 1

    def cuadro(self, pcbTable):
        lista = []

        for pcb in pcbTable:
            lista.append([pcb.path])
        return lista

    def __repr__(self):
        return tabulate(self._representacion, headers=self._headers, tablefmt='grid', stralign='center')
