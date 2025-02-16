#encoding:utf-8
from copy import deepcopy
from fractions import Fraction
from heapq import heapify, heappop
import time

BUMP_FACTOR = 1 / .95
incremental_nVars = 50

class cdcl_solver_s(object):
    # file表示文件输入，Clauses表示直接输入，nVars表示
    def __init__(self, file = None, nVars = incremental_nVars, nClauses = 0, Clauses = None):
        # init with a large variable number, when used out, extend it
        # we can use a variable map, maps the name of variable to index(from 1 to inf)
        # so that we can escape from a error input, e.g. clause, [1,-1000]
        # here, not implement for it is used in dpll(t) smt solver which name is 
        # already represented as index
        self.used_nVars = 0
        self.propagate_calls = 0
        self.add_times = 0

        if(Clauses is not None and file is not None):
            # from clauses and file at same time, it is an error!
            raise NotImplementedError()
        # 直接输入
        if(Clauses is not None):
            # init with the clauses and nVars, which call self._parse_formula()
            self.solver_init(nVars, len(Clauses))
            self._parse_formula(Clauses) # restart
            self.used_nVars = nVars
        # 文件输入
        elif(file is not None):
            # it will init in self.parse() or 
            self.parse(file) # restart
        else:
            # a deault settting(add clause by self.add_clause())
            self.solver_init(nVars, nClauses)

    # 初始化求解器
    def solver_init(self, nVars, nClauses):
        self.nVars = nVars
        self.nClauses = nClauses
        # 可以看到这边初始化了2*nVar个literals，分别表示正负文字
        self.literals = {i: Lit(i) for i in range(-nVars, nVars+1) if i != 0}
        self.var_inc = -1
        self.watchers = {i: [] for i in self.literals}
        self.clauses = []
        self.var_order = []

    # 扩展变量个数
    def extend(self, nVars = incremental_nVars):
        # once append 100 variable
        if(nVars < incremental_nVars): nVars = incremental_nVars
        self.nVars += nVars
        for i in range(-self.nVars, self.nVars+1):
            if(i!=0 and not i in self.literals):
                self.literals[i] = Lit(i)
                self.watchers[i] = []
    
    # 删除
    def delete(self):
        del self

    # 扩展约束
    def extend_formula(self, formula):
        for cl in formula:
            self.add_clause(cl)
    
    # 传播
    def propagate(self):
        # if(len(self.clauses)==0): return []
        # 最开始需要重启
        if(self.propagate_calls == 0): self.restart()
        self.propagate_calls += 1
        conflict = self._propagate()
        if(conflict):
            # conflict has happened
            if(self.level == 0):
                # the clauses are conflict
                return None
            else:
                # restart if it is not an error, but a current false assignment
                # 生成新的约束，并重启
                self.analyze(conflict)
                self.restart()
                return []
        else:
            # not conflict, propagate success => return a partial assignment
            return self.get_propagate_model()

    # 传播函数
    def _propagate(self):
        print('-------------------单位传播-------------------')
        # 存储可能的单位文字
        unit_literals = set()
        # level == 0: unit clause appears only in self.clauses
        # 初始化时，先寻找单位子句
        if(self.level == 0):
            for clause in self.clauses:
                # 若存在单位子句，则以该约束包含的文字作为决策文字
                if(clause.is_unit()):
                    lit = clause[0].to_int()
                    # 记录该文字
                    unit_literals.add(lit)
                    # 决策，在level0处添加当前lit
                    self.decisions[self.level].add(lit)
                    # 隐含图，当前lit指向level0以及其前继（导致它的clause中的其他元素的取值）
                    self.i_graph[lit] = (self.level, [])
        else:
            # 选择当前level的第一个文字作为单位文字
            lit = next(iter(self.decisions[self.level]))
            unit_literals.add(lit)
        print('当前单位文字：')
        if len(unit_literals) > 0:
            for i in unit_literals:
                print(i)
        else:
            print('don\'t have!')
        # 若存在单位文字
        while(len(unit_literals) > 0):
            # 取一个单位文字
            l = unit_literals.pop()
            if(self.literals[l].is_false()): return l
            # 将文字l赋值为真，他的反文字则为假
            print('文字', l, '被赋为真')
            self.literals[l].set_true()
            self.literals[-l].set_false()

            indexes = self.cur_watchers[l].copy()
            print('文字l赋值为false的约束如下：')
            # 对于包含文字l的约束
            for i in indexes:
                clause = self.clauses[i]
                print(clause)
                # 首先判断约束是否已满足
                if(clause.is_satisfied()):
                    print('该约束已满足')
                    continue
                # 然后判断传播后的约束是否可以继续单位传播
                elif(clause.is_unit()):
                    # 获取单位子句中的文字
                    unit_lit = clause.get_unset().to_int()
                    print('发现新的单位文字', unit_lit)
                    # 如果已经被选过则跳过
                    if unit_lit in self.i_graph:
                        print('但已被选择!')
                        continue
                    unit_literals.add(unit_lit)
                    self.decisions[self.level].add(unit_lit)
                    # reason表示导致unit_lit的文字赋值，比如1、2、3，若1为单位文字，则明显-2和-3赋值为真
                    reason = [-lit.to_int()
                            for lit in clause
                            if lit.to_int() != unit_lit]
                    self.i_graph[unit_lit] = (self.level, reason)
                # 若出现空子句，则发生冲突
                elif(clause.is_empty()):
                    # conflict
                    # 向decisions中添加l的反文字
                    print('发现冲突')
                    self.decisions[self.level].add(-l)
                    reason = [-lit.to_int()
                            for lit in clause
                            if lit.to_int() != -l]
                    self.i_graph[-l] = (self.level, reason)
                    # 直接返回了文字l，表示发生了冲突
                    return l
                # 不是上述情况
                else:
                    # clause not sat, modify watchers
                    # 修改watchers，
                    thing = iter(clause)
                    while(True):
                        lit = next(thing)
                        # 如果lit被赋值，则跳过该文字
                        if(not lit.is_unset()):
                            continue
                        lit = lit.to_int()
                        # 如果当前约束中存在-lits，则跳过
                        if(i in self.cur_watchers[-lit]):
                            continue
                        # 文字l的cur_watchers去掉当前约束i，因为l在该约束中已赋值了
                        self.cur_watchers[l].remove(i)
                        # 这边没搞懂，比如cluseA包含1、2、3，l=1，2、3未赋值，则-2和-3的cur_watchers添加A
                        self.cur_watchers[-lit].append(i)
                        break
        # self.print_info()
        # self.print_i_graph()
        return False
    
    # 重启
    def restart(self):
        # 重置文字赋值
        for lit in self.literals.values():
            lit.unset()
        # 通过cur_var_order记录var_order
        self.cur_var_order = deepcopy(self.var_order) # initial when used, not here
        # var_order_finder是cur_var_order的哈希表，方便查询
        self.var_order_finder = {lit: i for i, [p, lit] in enumerate(self.cur_var_order)}
        # 通过cur_watchers记录watchers
        self.cur_watchers = deepcopy(self.watchers)
        # 重置决策及隐含图
        self.decisions = {0: set()}
        self.i_graph = {}
        # 重置决策序列及传播次数
        self.level = 0
        self.propagate_calls = 0 
    
    # 判断是否满足
    def satisfied(self):
        return all(clause.is_satisfied() for clause in self.clauses)

    # 决策方法
    def decide(self):
        # 将cur_var_order转换为小根堆
        heapify(self.cur_var_order)
        # self.cur_var_order is []
        next_lit = 0
        # 根据cur_var_order找到第一个未赋值的文字，从小到大排列
        for _ in range(len(self.cur_var_order)):
            lit = heappop(self.cur_var_order)[1]
            if(self.literals[lit].is_unset()):
                next_lit = lit
                break
        # lit->i，通过lit索引i，哈希
        self.var_order_finder = {lit: i for i, (p, lit) in enumerate(self.cur_var_order)}

        if(not next_lit):
            raise Exception('unable to choose literal')
        # 做出决策，决策序列加一
        self.level += 1
        self.decisions[self.level] = {next_lit}
        self.i_graph[next_lit] = (self.level, [])

    # 分析方法，找到1-UIP，并添加新clause
    def analyze(self, l):
        # find first unique implication point (1-UIP)
        uips = set()
        weights = {lit: Fraction() for lit in self.decisions[self.level]}

        def explore(lit, weight):
            weights[lit] += weight
            # 寻找导致当前lit的当前level的决策变量
            next_lits = [next_lit
                        for next_lit in self.i_graph[lit][1]
                        if self.i_graph[next_lit][0]==self.level]
            # 递归寻找（以增加权重的形式）
            for next_lit in next_lits:
                explore(next_lit, weight / len(next_lits))
        # 通过explore函数可以给当前level的各个文字赋予权重
        explore(l, Fraction(1.))
        # 权重为1的即UIP
        for lit in weights.keys():
            if(weights[lit] == Fraction(1.)):
                uips.add(lit)
            uips.discard(l)

        lit = l
        # 寻找first-UIP，和explore函数类似的思路，寻找到的第一个uip即first-uip
        while(True):
            for next_lit in self.i_graph[lit][1]:
                if(self.i_graph[next_lit][0] == self.level):
                    lit = next_lit
                    break
            if(lit in uips):
                fuip = lit
                break

        # find cut
        new_clause = {-fuip}

        def find_cut(lit):
            # 若lit不属于当前level，则向new_clause中添加该lit，表示两者不能共存
            if(self.i_graph[lit][0]!=self.level):
                new_clause.add(-lit)
                return
            # 若到达fuip，返回
            if(lit == fuip):
                return
            
            for next_lit in self.i_graph[lit][1]:
                find_cut(next_lit)
        
        # 对l的正负文字都采用find_cut方法
        find_cut(l)
        find_cut(-l)

        self._addClause(new_clause)

    # 添加约束
    def add_clause(self, clause):
        self.add_times += 1
        # 判断是否扩展
        has_extend = False
        for i in clause:
            if(abs(i) > self.used_nVars):
                has_extend = True
                self.used_nVars = abs(i)
            if(abs(i) > self.nVars):
                self.extend(abs(i)-self.nVars)

        if(not has_extend):
            self._addClause(clause)
            return

        self.clauses.append(Clause([self.literals[lit] for lit in clause]))
        clause_idx = len(self.clauses)-1
        clause_iter = iter(self.clauses[-1])

        # add to watcher, the first two literals
        for _ in range(min(2, len(clause))):
            lit = next(clause_iter)
            self.watchers[-lit.to_int()].append(clause_idx)

        # add to var_order
        # temp dict for maps the bump factor to the literal
        heap_dict = {i: 1. for i in clause}
        for lit in clause:
            heap_dict[lit] += self.var_inc
        for i in heap_dict:
            if(i in self.var_order_finder):
                # if append before
                idx = self.var_order_finder[i]
                self.var_order[idx][0] += heap_dict[i]
            else:
                self.var_order_finder[i] = len(self.var_order)  
                self.var_order.append([heap_dict[i], i])

    # 添加约束
    def _addClause(self, clause):
        # 添加约束
        self.clauses.append(Clause([self.literals[lit] for lit in clause]))
        clause_idx = len(self.clauses)-1
        clause_iter = iter(clause)
        # 更新watchers
        for _ in range(min(2, len(clause))):
            lit = next(clause_iter)
            self.watchers[-lit].append(clause_idx)
        self.var_inc*=BUMP_FACTOR
        # 更新变量序，若clause过多，需要进行缩小处理
        for lit in clause:
            if(lit not in self.var_order_finder):
                continue

            var_order_item = self.cur_var_order[self.var_order_finder[lit]]
            var_order_item[0] += self.var_inc

            # if bump factor is too large, var_increment down
            if(var_order_item[0]>1e100):
                self.var_inc *= 1e-100

                for item in self.cur_var_order:
                    item[0] *= 1e-100

    # 求解方法，很简洁
    def solve(self) -> bool:
        print('-------------------开始求解-------------------')
        # self.restart() # restart before, after parse_file or parse_formula
        while(True):
            # 单位传播
            conflict = self._propagate()
            # 发生冲突
            if(conflict):
                # 若在开始时就发生冲突，则肯定不满足
                if(self.level==0):
                    return False
                else:
                    # 分析冲突，添加冲突子句
                    self.analyze(conflict)
                    # 重启
                    self.restart()
            # 未发生冲突
            else:
                if(self.satisfied()):
                    return True
                else:
                    # 开始进行决策
                    self.decide()

    # 得到传播后的已赋值变量
    def get_propagate_model(self):
        model = []
        for i in range(2, self.used_nVars+1):
            if(not self.literals[i].is_unset()):
                if(self.literals[i].is_false()):
                    model.append(-i)
                else:
                    model.append(i)
        return model

    # 得到变量赋值
    def get_model(self):
        model = [l for l in self.i_graph]
        self.model = []
        self.model.extend([-l if -l in model else l
                        for l in range(1, self.used_nVars+1)])
        return self.model

    # 以clauses作为输入时调用
    def _parse_formula(self, clauses):
        for clause in clauses:
            self.clauses.append(Clause(list({self.literals[int(x)]
                                        for x in clause})))
        
        # temp dict for maps the bump factor to the literal
        heap_dict = {i: 1. for i in self.literals}
        for i, clause in enumerate(self.clauses):
            for lit in clause:
                heap_dict[lit.to_int()] += self.var_inc
            
            # watchers is watching first two literals of all clauses
            for j in range(min(2, len(clause))):
                lit = clause[j]
                self.watchers[-lit.to_int()].append(i)
        # var order maps bump factor to the literal
        self.var_order = [[p, lit] for lit, p in heap_dict.items()]
        self.restart()

    # 导入文件
    def parse(self, file):
        print('-------------------处理文件', file, '-------------------')
        f = open(file, 'r')
        lines = f.readlines()
        f.close()
        # escape the comment line
        lines = [line for line in lines if line[0]!='c' or line[0]!='\n']
        index = 0
        # 第一行为参数
        params = lines[0].split()
        if(len(params)!=0 and params[0]=='p' and params[1]=='cnf'):
            # 输入分别为变量个数nVar、约束个数nClause
            self.solver_init(int(params[2]), int(params[3]))
            # 已用变量个数也初始化为变脸个数nVar
            self.used_nVars = int(params[2])
            index += 1
        # 处理输入约束
        nZeros = int(self.nClauses)
        while(nZeros>0):
            # if commend line or blank line, may raise error
            clause = [int(x) for x in lines[index].split()]
            # delete the final zero, e.g. 1 -2 3 0
            clause = clause[:-1]
            # append to self.clauses
            self.clauses.append(Clause(list({self.literals[int(x)] for x in clause})))
            nZeros -= 1
            index += 1
        
        # temp dict for maps the bump factor to the literal
        # 记录约束中各文字的次数
        heap_dict = {i: 1. for i in self.literals}
        for i, clause in enumerate(self.clauses):
            for lit in clause:
                # var_inc是负数，所以变量顺序还是按照有多到少排列的
                heap_dict[lit.to_int()] += self.var_inc
            
            # watchers is watching first two literals of all clauses
            # watchers会记录约束中前两个文字对应的约束索引，但是是反着记录的
            for j in range(min(2, len(clause))):
                lit = clause[j]
                self.watchers[-lit.to_int()].append(i)
        # var order maps bump factor to the literal
        
        # test_order
        heap_dict[8] += -100
        heap_dict[2] += -90
        heap_dict[9] += -80
        heap_dict[1] += -70
        
        # 利用heap_dict生成变量序，启发式
        self.var_order = [[p, lit] for lit, p in heap_dict.items()]
        
        # self.print_info()
        self.restart()

    def print_info(self):
        print('-------------------var_order-------------------')
        print(self.var_order)
        print('-------------------clauses-------------------')
        for clause in self.clauses:
            print(clause)
        print('-------------------literals-------------------')
        for literal in self.literals:
            print(literal)

    def print_i_graph(self):
        print('-------------------i_graph-------------------')
        for i,v in self.i_graph.items():
            print(i, ':', v[0], v[1])

# 约束的数据结构，其中lits表示约束包含的文字的列表
class Clause:
    def __init__(self, lits):
        self.lits = lits

    def __getitem__(self, key):
        return self.lits[key]
    

    def __len__(self):
        return len(self.lits)
    # 是否为单位子句，只统计未赋值的文字，所以需要先判断是否已满足
    def is_unit(self):
        return sum(lit.is_unset() for lit in self.lits) == 1

    def __iter__(self):
        yield from self.lits
    # 判断约束是否满足
    def is_satisfied(self):
        return any(lit.is_true() for lit in self.lits)
    # 判断约束是否为空子句（即不可满足）
    def is_empty(self):
        return all(lit.is_false() for lit in self.lits)
    # 获取约束中未赋值的文字
    def get_unset(self):
        for lit in self.lits:
            if lit.is_unset():
                return lit

    def __str__(self):
        ans = ""
        for i in self.lits:
            ans += str(i) + " "
        
        return ans[:-1]

# 文字的数据结构，其中value表示文字的取值，lit表示文字的标签
class Lit:
    # 初始化时文字不赋值
    def __init__(self, lit):
        self.lit = lit
        self.value = 0

    def set_true(self):
        self.value = 1

    def set_false(self):
        self.value = -1

    def unset(self):
        self.value = 0

    def is_true(self):
        return self.value == 1

    def is_false(self):
        return self.value == -1

    def is_unset(self):
        return self.value == 0
    # 返回文字的标签
    def to_int(self):
        return self.lit

    def __str__(self):
        return str(self.lit)

def test(solver, f, start):
    lines = []
    nVars = 0
    nClauses = 0
    with open(f) as file:
        lines = file.readlines()
    lines = [line for line in lines if line[0]!='c' or line[0]!='\n']
    index = 0
    params = lines[0].split()
    if(len(params)!=0 and params[0]=='p' and params[1]=='cnf'):
        nVars = int(params[2])
        nClauses = int(params[3])
        index += 1
    nZeros = int(nClauses)
    while(nZeros>0):
        # if commend line or blank line, may raise error
        clause = [int(x) for x in lines[index].split()]
        # delete the final zero, e.g. 1 -2 3 0
        clause = clause[:-1]
        # append to self.clauses
        solver.add_clause(clause)
        end = time.clock()
        print(end-start)
        start = end
        nZeros -= 1
        index += 1
    
    print(s.propagate())
    print(time.clock()-start)

if(__name__=="__main__"):
    s = cdcl_solver_s(file="./test6.cnf")

    f = s.solve()
    print(f)
    if(f):
        print(s.get_model())
    else:
        print(None)

    
    # s.add_clause([1,2,3])
    # s.add_clause([-2,-3])
    # s.add_clause([1])
    # s.add_clause([-1])
    # print(s.propagate())
    
    # start = time.clock()
    # test(s, 'test5.cnf', start)


    

# based on chapter 2 of decision procedure
# based on chapter 4 of handbook of satisfiability
# based on https://github.com/soedirgo/sat-solver
# based on https://github.com/zacsimile/SATisPy
# based on https://github.com/marijnheule/microsat/