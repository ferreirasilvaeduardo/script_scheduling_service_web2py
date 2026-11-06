DECLARE
  v_linha      VARCHAR2(32767);
  v_cabecalho  VARCHAR2(32767);
  v_pedaco     VARCHAR2(200);
  v_pos        PLS_INTEGER;
  v_tam        PLS_INTEGER;
  v_limite     CONSTANT PLS_INTEGER := 200;  -- < 255 (limite do DBMS_OUTPUT)

  ------------------------------------------------------------------
  -- Escapa um valor para CSV no padrão "quote all":
  --   - duplica aspas duplas
  --   - substitui CR/LF por espaço
  --   - envolve o valor em aspas duplas
  ------------------------------------------------------------------
  FUNCTION escapa(p_valor IN VARCHAR2) RETURN VARCHAR2 IS
    v_valor VARCHAR2(32767);
  BEGIN
    IF p_valor IS NULL THEN
      RETURN '""';
    END IF;
    v_valor := p_valor;
    v_valor := REPLACE(v_valor, '"', '""');      -- duplica aspas
    v_valor := REPLACE(v_valor, CHR(13), ' ');   -- remove CR
    v_valor := REPLACE(v_valor, CHR(10), ' ');   -- remove LF
    RETURN '"' || v_valor || '"';
  END escapa;

  ------------------------------------------------------------------
  -- Emite uma linha longa em pedaços de 200 bytes, sem newline
  -- intermediário, e só quebra no final com NEW_LINE.
  ------------------------------------------------------------------
  PROCEDURE emite_linha(p_linha IN VARCHAR2) IS
    v_pos  PLS_INTEGER := 1;
    v_tam  PLS_INTEGER := LENGTH(p_linha);
  BEGIN
    IF v_tam = 0 THEN
      DBMS_OUTPUT.NEW_LINE;
      RETURN;
    END IF;
    WHILE v_pos <= v_tam LOOP
      DBMS_OUTPUT.PUT(SUBSTR(p_linha, v_pos, v_limite));
      v_pos := v_pos + v_limite;
    END LOOP;
    DBMS_OUTPUT.NEW_LINE;
  END emite_linha;

BEGIN
  -- Cabeçalho: sem aspas, só os nomes separados por |
  v_cabecalho :=
       'EMPS_COD'          || '[trdl]' ||
       'FILI_COD'          || '[trdl]' ||
       'FILI_COD_CGC'      || '[trdl]' ||
       'UNFE_SIG'          || '[trdl]' ||
       'FILI_COD_INSEST'   || '[trdl]' ||
       'FILI_COD_INSMUN'   || '[trdl]' ||
       'FILI_COD_ATIVECON' || '[trdl]' ||
       'FILI_NOM'          || '[trdl]' ||
       'FILI_NOM_FANTASIA' || '[trdl]' ||
       'FILI_END'          || '[trdl]' ||
       'FILI_END_NUM'      || '[trdl]' ||
       'FILI_END_COMP'     || '[trdl]' ||
       'FILI_END_BAIRRO'   || '[trdl]' ||
       'FILI_END_MUNIC'    || '[trdl]' ||
       'FILI_END_CEP'      || '[trdl]' ||
       'FILI_COD_LOCAL'    || '[trdl]' ||
       'FILI_FAX'          || '[trdl]' ||
       'FILI_TEL'          || '[trdl]' ||
       'TP_LOC'            || '[trdl]' ||
       'FILI_SETOR'        || '[trdl]' ||
       'FILI_AUTOR'        || '[trdl]' ||
       'FILI_SANITARIA'    || '[trdl]' ||
       'FILI_LICEN'        || '[trdl]' ||
       'FILI_ESPEC'        || '[trdl]' ||
       'FILI_IND_RET_ISS'  || '[trdl]' ||
       'FILI_COD_INSCEN'   || '[trdl]' ||
       'FILI_EMAIL'        || '[trdl]' ||
       'FILI_NAT_JUR'      || '[trdl]' ||
       'NUM01'             || '[trdl]' ||
       'NUM02'             || '[trdl]' ||
       'NUM03'             || '[trdl]' ||
       'VAR01'             || '[trdl]' ||
       'VAR02'             || '[trdl]' ||
       'VAR03'             || '[trdl]' ||
       'VAR04'             || '[trdl]' ||
       'VAR05'             || '[trdl]' ||
       'FILI_CEI'          || '[trdl]' ||
       'FILI_NIT'          || '[trdl]' ||
       'FILI_SUFRAMA'      || '[trdl]' ||
       'FILI_MUN_IBGE'     || '[trdl]' ||
       'TPLD_COD'          || '[trdl]' ||
       'FILI_NIRE'         || '[trdl]' ||
       'FILI_MATRIZ'       || '[trdl]' ||
       'FILI_TIP_ATI_ECO'  || '[trdl]' ||
       'FILI_INFO_COMPL'   || '[trdl]' ||
       'FILI_CLAS_TRIB'    || '[trdl]' ||
       'FILI_IND_OB_CIVIL' || '[trdl]' ||
       'FILI_COD_CNPJ_EFR' || '[trdl]' ||
       'SIST_ORIGEM'       || '[trdl]' ||
       'USUA_ORIGEM'       || '[trdl]' ||
       'DATA_CRIACAO'      || '[trdl]' ||
       'ID_ORIGEM'         || '[trdl]' ||
       'FILI_CLAS_IND_EQ'  || '[trdl]' ||
       'FILI_DEF_BC_ST';

  emite_linha(v_cabecalho);

  FOR v_reg IN (
    SELECT EMPS_COD, FILI_COD, FILI_COD_CGC, UNFE_SIG, FILI_COD_INSEST,
           FILI_COD_INSMUN, FILI_COD_ATIVECON, FILI_NOM, FILI_NOM_FANTASIA,
           FILI_END, FILI_END_NUM, FILI_END_COMP, FILI_END_BAIRRO, FILI_END_MUNIC,
           FILI_END_CEP, FILI_COD_LOCAL, FILI_FAX, FILI_TEL, TP_LOC, FILI_SETOR,
           FILI_AUTOR, FILI_SANITARIA, FILI_LICEN, FILI_ESPEC, FILI_IND_RET_ISS,
           FILI_COD_INSCEN, FILI_EMAIL, FILI_NAT_JUR, NUM01, NUM02, NUM03,
           VAR01, VAR02, VAR03, VAR04, VAR05, FILI_CEI, FILI_NIT, FILI_SUFRAMA,
           FILI_MUN_IBGE, TPLD_COD, FILI_NIRE, FILI_MATRIZ, FILI_TIP_ATI_ECO,
           FILI_INFO_COMPL, FILI_CLAS_TRIB, FILI_IND_OB_CIVIL, FILI_COD_CNPJ_EFR,
           SIST_ORIGEM, USUA_ORIGEM, DATA_CRIACAO, ID_ORIGEM, FILI_CLAS_IND_EQ,
           FILI_DEF_BC_ST
      FROM openrisow.filial
     WHERE 1=1 -- and '1' = '[a]' AND 'b' = '[b]'   -- [trcx] - [trscript] - [trdirscript] - [trrel] - [trdirrel] - [trst] - [trzip] - [trkp] - [trdl] - [trtpex] - [trfertpex] - [trnlsl] - [trql] -
  ) LOOP
    v_linha :=
         escapa(NVL(TO_CHAR(v_reg.EMPS_COD),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_CGC),''))        || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.UNFE_SIG),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_INSEST),''))     || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_INSMUN),''))     || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_ATIVECON),''))   || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_NOM),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_NOM_FANTASIA),''))   || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_END),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_END_NUM),''))        || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_END_COMP),''))       || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_END_BAIRRO),''))     || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_END_MUNIC),''))      || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_END_CEP),''))        || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_LOCAL),''))      || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_FAX),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_TEL),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.TP_LOC),''))              || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_SETOR),''))          || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_AUTOR),''))          || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_SANITARIA),''))      || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_LICEN),''))          || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_ESPEC),''))          || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_IND_RET_ISS),''))    || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_INSCEN),''))     || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_EMAIL),''))          || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_NAT_JUR),''))        || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.NUM01),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.NUM02),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.NUM03),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.VAR01),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.VAR02),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.VAR03),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.VAR04),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.VAR05),''))               || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_CEI),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_NIT),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_SUFRAMA),''))        || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_MUN_IBGE),''))       || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.TPLD_COD),''))            || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_NIRE),''))           || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_MATRIZ),''))         || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_TIP_ATI_ECO),''))    || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_INFO_COMPL),''))     || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_CLAS_TRIB),''))      || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_IND_OB_CIVIL),''))   || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_COD_CNPJ_EFR),''))   || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.SIST_ORIGEM),''))         || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.USUA_ORIGEM),''))         || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.DATA_CRIACAO,'DD/MM/YYYY HH24:MI:SS'),'')) || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.ID_ORIGEM),''))           || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_CLAS_IND_EQ),''))    || '[trdl]' ||
         escapa(NVL(TO_CHAR(v_reg.FILI_DEF_BC_ST),''));

    emite_linha(v_linha);
  END LOOP;
END;
/